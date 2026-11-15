"""Conversations and the Prayer Wall: posts written by members of the main site, with replies.

The two are boards of one table (conversation_posts.board, 'conversations' or 'prayer'): the same rules, the
same people, but a post shows only on its own board. A reply belongs to its post, so it is on that board.

Only accounts an administrator allowed (users.use_conversations) may write; main.py checks that on every
endpoint that writes. Anyone reads every post and reply, except a private Prayer Wall post, and a member may reply
to any post they can see; only the author of a post or reply can change or delete it, and anyone else is told it was not found, as
with notes. Deleting a post deletes its replies. A post has a title and a body, a reply only a body: a little
HTML from the editor (Quill), cleaned before it is kept (contact.check_rich_text), so it is safe to show.

A Prayer Wall post has three choices (migration 035; all off on Conversations): anonymous (shown as "Anonymous";
its author's name is not searched), private (seen only by its author, in the Drupal admin and in the prayer list
email of the site's administrators, users.see_private_prayers) and "email to the prayer list" (prayer_list.py
sends it to every subscriber). listed_at is when it was made private or emailed, whichever came last. Its
author can also mark it answered at any time, without editing it (answered_at; an answered request is not emailed).

A Conversations post has "Email me replies" (email_replies, migration 036; off unless ticked): each new reply by
someone else is emailed to its author (send_reply_email, run by main.py after answering), with a link that turns it
off (reply_email_token, handled by subscriptions.unsubscribe_with_token).
"""

import logging
import secrets
from email.message import EmailMessage

from accounts import site_link
from contact import ContactProblem, MailUnavailable, check_rich_text, load_mail_settings, send_email
from search import connect
from site_settings import get_public_settings
import sms

logger = logging.getLogger("conversations")

TITLE_LIMIT = 200
POST_TEXT_LIMIT = 20000
POST_HTML_LIMIT = 120000
REPLY_TEXT_LIMIT = 5000
REPLY_HTML_LIMIT = 30000
# Plenty for any member; they stop one account from filling the database.
MAX_POSTS_PER_USER = 1000
MAX_REPLIES_PER_USER = 5000
PER_PAGE_LIMIT = 50
BOARDS = ("conversations", "prayer")
QUERY_WORD_LIMIT = 10

# An author's name is read with the post or reply, so a changed name shows everywhere. An account with no name
# shows as "A member": the email address is never shown to other members.
_AUTHOR = "COALESCE(NULLIF(concat_ws(' ', users.first_name, users.last_name), ''), 'A member')"
ANONYMOUS = "Anonymous"
_COLUMNS = f"""
  conversation_posts.id, conversation_posts.user_id, conversation_posts.title, conversation_posts.body,
  conversation_posts.created_at, conversation_posts.updated_at, {_AUTHOR}, conversation_posts.board,
  conversation_posts.is_anonymous, conversation_posts.is_private, conversation_posts.email_to_prayer_list,
  conversation_posts.answered_at, conversation_posts.email_replies
"""
# What a viewer may see: every post but the private ones of others.
_VISIBLE = "(NOT conversation_posts.is_private OR conversation_posts.user_id = %(viewer)s)"
_FROM = "conversation_posts JOIN users ON users.id = conversation_posts.user_id"
_REPLY_COLUMNS = f"""
  conversation_replies.id, conversation_replies.user_id, conversation_replies.post_id, conversation_replies.body,
  conversation_replies.created_at, conversation_replies.updated_at, {_AUTHOR}
"""
_REPLY_FROM = "conversation_replies JOIN users ON users.id = conversation_replies.user_id"


class ConversationProblem(Exception):
  """The request cannot be done; the text says why and is fit to show the member."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def _row_to_post(row, viewer_id: int) -> dict:
  return {
    "id": row[0],
    "title": row[2],
    "body": row[3],
    "created_at": row[4].isoformat(),
    "updated_at": row[5].isoformat(),
    # An anonymous post's author is not given, even to its author (the page adds "you").
    "author": ANONYMOUS if row[8] else row[6],
    "board": row[7],
    # Whether the member asking wrote it (the page then offers Edit and Delete).
    "is_mine": row[1] == viewer_id,
    "is_anonymous": row[8],
    "is_private": row[9],
    "email_to_prayer_list": row[10],
    # When its author marked it answered, or None.
    "answered_at": row[11].isoformat() if row[11] else None,
    # Whether new replies are emailed to the author (told only to the author).
    "email_replies": row[12] and row[1] == viewer_id,
    "replies": [],
  }


def _row_to_reply(row, viewer_id: int) -> dict:
  return {
    "id": row[0],
    "post_id": row[2],
    "body": row[3],
    "created_at": row[4].isoformat(),
    "updated_at": row[5].isoformat(),
    "author": row[6],
    "is_mine": row[1] == viewer_id,
  }


def _with_replies(connection, posts: list[dict], viewer_id: int) -> list[dict]:
  """Adds each post's replies, oldest first, in one query for the whole page."""
  by_id = {post["id"]: post for post in posts}
  if by_id:
    rows = connection.execute(
      f"""
      SELECT {_REPLY_COLUMNS} FROM {_REPLY_FROM} WHERE conversation_replies.post_id = ANY(%s)
      ORDER BY conversation_replies.created_at, conversation_replies.id
      """,
      (list(by_id),),
    ).fetchall()
    for row in rows:
      by_id[row[2]]["replies"].append(_row_to_reply(row, viewer_id))
  return posts


def _checked_board(board: str) -> str:
  if board not in BOARDS:
    raise ConversationProblem("There is no such board.", 404)
  return board


def _checked_title(title: str) -> str:
  title = " ".join((title or "").split())
  if not title:
    raise ConversationProblem("Please give the post a title.")
  if len(title) > TITLE_LIMIT:
    raise ConversationProblem(f"The title can be up to {TITLE_LIMIT} characters.")
  return title


def _checked_options(board: str, is_anonymous: bool, is_private: bool, email_to_prayer_list: bool) -> tuple[bool, bool, bool]:
  """The Prayer Wall choices, which only a Prayer Wall post has; a private post is never emailed."""
  if board != "prayer":
    if is_anonymous or is_private or email_to_prayer_list:
      raise ConversationProblem("Only Prayer Wall posts can be anonymous, private or emailed.")
    return False, False, False
  if is_private and email_to_prayer_list:
    raise ConversationProblem("A private request is not emailed: untick one of the two.")
  return is_anonymous, is_private, email_to_prayer_list


def _checked_email_replies(board: str, email_replies: bool) -> bool:
  if email_replies and board != "conversations":
    raise ConversationProblem("Only Conversations posts can have their replies emailed.")
  return email_replies


def _cleaned(body: str, html_limit: int, text_limit: int, what: str) -> dict:
  try:
    return check_rich_text(body, html_limit, text_limit, what)
  except ContactProblem as problem:
    raise ConversationProblem(str(problem)) from problem


def _get(connection, post_id: int, viewer_id: int) -> dict:
  row = connection.execute(f"SELECT {_COLUMNS} FROM {_FROM} WHERE conversation_posts.id = %s", (post_id,)).fetchone()
  return _with_replies(connection, [_row_to_post(row, viewer_id)], viewer_id)[0]


def create_post(
  user_id: int,
  title: str,
  body: str,
  board: str = "conversations",
  is_anonymous: bool = False,
  is_private: bool = False,
  email_to_prayer_list: bool = False,
  email_replies: bool = False,
) -> dict:
  board = _checked_board(board)
  is_anonymous, is_private, email_to_prayer_list = _checked_options(board, is_anonymous, is_private, email_to_prayer_list)
  email_replies = _checked_email_replies(board, email_replies)
  title = _checked_title(title)
  cleaned = _cleaned(body, POST_HTML_LIMIT, POST_TEXT_LIMIT, "post")
  with connect() as connection:
    count = connection.execute("SELECT count(*) FROM conversation_posts WHERE user_id = %s", (user_id,)).fetchone()[0]
    if count >= MAX_POSTS_PER_USER:
      raise ConversationProblem(f"You have reached the limit of {MAX_POSTS_PER_USER} posts. Please delete some first.")
    post_id = connection.execute(
      """
      INSERT INTO conversation_posts
        (user_id, title, body, body_text, board, is_anonymous, is_private, email_to_prayer_list, listed_at,
         email_replies, reply_email_token)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() END, %s, CASE WHEN %s THEN %s END) RETURNING id
      """,
      (
        user_id, title, cleaned["html"], cleaned["text"], board, is_anonymous, is_private, email_to_prayer_list,
        email_to_prayer_list or is_private, email_replies, email_replies, secrets.token_urlsafe(24),
      ),
    ).fetchone()[0]
    return _get(connection, post_id, user_id)


def _like_pattern(word: str) -> str:
  """A word as a LIKE pattern that matches it anywhere, with %, _ and the escape itself taken literally."""
  escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
  return f"%{escaped}%"


def _search_conditions(words: list[str], include_email: bool = False) -> tuple[list[str], dict]:
  """One condition per word: the word is in the post's title or text, its author's name (or, for the admin page,
  address) or the text of one of its replies. The values are named, since each word is used several times.
  On the public site an anonymous post's author is not searched (it would give the name away)."""
  conditions = []
  values = {}
  for number, word in enumerate(words):
    name = f"%(word_{number})s"
    values[f"word_{number}"] = _like_pattern(word)
    email = f" OR users.email ILIKE {name}" if include_email else ""
    named = "true" if include_email else "NOT conversation_posts.is_anonymous"
    conditions.append(
      f"""(
        conversation_posts.title ILIKE {name} OR conversation_posts.body_text ILIKE {name}
        OR ({named} AND concat_ws(' ', users.first_name, users.last_name) ILIKE {name}){email}
        OR EXISTS (
          SELECT 1 FROM conversation_replies
          WHERE conversation_replies.post_id = conversation_posts.id AND conversation_replies.body_text ILIKE {name}
        )
      )"""
    )
  return conditions, values


def list_posts(
  viewer_id: int, query: str | None = None, only_mine: bool = False, page: int = 1, per_page: int = 10, board: str = "conversations"
) -> dict:
  """Every member's posts on one board with their replies, newest post first, one page of them: {"posts",
  "total", "page", "per_page"}.

  query keeps the posts that have every word of it, in any case and any part of a word, in the title, the
  text, the author's name or a reply. only_mine keeps the viewer's own posts."""
  if page < 1 or not 1 <= per_page <= PER_PAGE_LIMIT:
    raise ConversationProblem(f"Pages are from 1 to {PER_PAGE_LIMIT} posts.")
  words = (query or "").split()
  if len(words) > QUERY_WORD_LIMIT:
    raise ConversationProblem(f"Please search for up to {QUERY_WORD_LIMIT} words.")
  conditions, values = _search_conditions(words)
  conditions.append("conversation_posts.board = %(board)s")
  values["board"] = _checked_board(board)
  conditions.append(_VISIBLE)
  values["viewer"] = viewer_id
  if only_mine:
    conditions.append("conversation_posts.user_id = %(viewer)s")
  where = " AND ".join(conditions) or "true"
  with connect() as connection:
    total = connection.execute(f"SELECT count(*) FROM {_FROM} WHERE {where}", values).fetchone()[0]
    rows = connection.execute(
      f"""
      SELECT {_COLUMNS} FROM {_FROM} WHERE {where}
      ORDER BY conversation_posts.created_at DESC, conversation_posts.id DESC LIMIT %(limit)s OFFSET %(offset)s
      """,
      {**values, "limit": per_page, "offset": (page - 1) * per_page},
    ).fetchall()
    posts = _with_replies(connection, [_row_to_post(row, viewer_id) for row in rows], viewer_id)
  return {"posts": posts, "total": total, "page": page, "per_page": per_page}


def update_post(
  user_id: int,
  post_id: int,
  title: str,
  body: str,
  is_anonymous: bool = False,
  is_private: bool = False,
  email_to_prayer_list: bool = False,
  email_replies: bool = False,
) -> dict:
  """Replaces the title, text and Prayer Wall choices (or, on Conversations, "email me replies") of one of the
  member's own posts. Turning the email on puts
  the post in the subscribers' next prayer list email (again, if it was turned off and on); making it private puts
  it in the administrators' next one."""
  title = _checked_title(title)
  cleaned = _cleaned(body, POST_HTML_LIMIT, POST_TEXT_LIMIT, "post")
  with connect() as connection:
    found = connection.execute("SELECT board FROM conversation_posts WHERE id = %s AND user_id = %s", (post_id, user_id)).fetchone()
    if found is None:
      raise ConversationProblem("That post was not found.", 404)
    is_anonymous, is_private, email_to_prayer_list = _checked_options(found[0], is_anonymous, is_private, email_to_prayer_list)
    email_replies = _checked_email_replies(found[0], email_replies)
    connection.execute(
      """
      UPDATE conversation_posts SET title = %(title)s, body = %(html)s, body_text = %(text)s, updated_at = now(),
        is_anonymous = %(anonymous)s, is_private = %(private)s,
        listed_at = CASE
          WHEN NOT (%(email)s OR %(private)s) THEN NULL
          WHEN (%(email)s AND NOT email_to_prayer_list) OR (%(private)s AND NOT is_private) THEN now()
          ELSE listed_at
        END,
        email_to_prayer_list = %(email)s,
        email_replies = %(replies)s,
        reply_email_token = CASE WHEN %(replies)s THEN COALESCE(reply_email_token, %(token)s) ELSE reply_email_token END
      WHERE id = %(post)s AND user_id = %(user)s
      """,
      {
        "title": title, "html": cleaned["html"], "text": cleaned["text"], "anonymous": is_anonymous,
        "private": is_private, "email": email_to_prayer_list, "replies": email_replies,
        "token": secrets.token_urlsafe(24), "post": post_id, "user": user_id,
      },
    )
    return _get(connection, post_id, user_id)


def set_answered(user_id: int, post_id: int, answered: bool) -> dict:
  """Marks one of the member's own Prayer Wall requests answered, or not, without changing anything else (the
  author ticks a box on the post; no editing). It keeps the first time it was marked answered."""
  with connect() as connection:
    found = connection.execute("SELECT board FROM conversation_posts WHERE id = %s AND user_id = %s", (post_id, user_id)).fetchone()
    if found is None:
      raise ConversationProblem("That post was not found.", 404)
    if found[0] != "prayer":
      raise ConversationProblem("Only Prayer Wall requests can be marked answered.")
    connection.execute(
      """
      UPDATE conversation_posts SET answered_at = CASE WHEN %s THEN COALESCE(answered_at, now()) END
      WHERE id = %s AND user_id = %s
      """,
      (answered, post_id, user_id),
    )
    return _get(connection, post_id, user_id)


def delete_post(user_id: int, post_id: int) -> None:
  """Deletes one of the member's own posts, with every reply to it."""
  with connect() as connection:
    deleted = connection.execute(
      "DELETE FROM conversation_posts WHERE id = %s AND user_id = %s RETURNING id", (post_id, user_id)
    ).fetchone()
  if deleted is None:
    raise ConversationProblem("That post was not found.", 404)


def _get_reply(connection, reply_id: int, viewer_id: int) -> dict:
  row = connection.execute(f"SELECT {_REPLY_COLUMNS} FROM {_REPLY_FROM} WHERE conversation_replies.id = %s", (reply_id,)).fetchone()
  return _row_to_reply(row, viewer_id)


def create_reply(user_id: int, post_id: int, body: str) -> dict:
  """Adds the member's reply to any post."""
  cleaned = _cleaned(body, REPLY_HTML_LIMIT, REPLY_TEXT_LIMIT, "reply")
  with connect() as connection:
    # A private post is "not found" to anyone but its author.
    if not connection.execute(
      f"SELECT 1 FROM conversation_posts WHERE id = %(post)s AND {_VISIBLE}", {"post": post_id, "viewer": user_id}
    ).fetchone():
      raise ConversationProblem("That post was not found. It may have been deleted.", 404)
    count = connection.execute("SELECT count(*) FROM conversation_replies WHERE user_id = %s", (user_id,)).fetchone()[0]
    if count >= MAX_REPLIES_PER_USER:
      raise ConversationProblem(f"You have reached the limit of {MAX_REPLIES_PER_USER} replies. Please delete some first.")
    reply_id = connection.execute(
      "INSERT INTO conversation_replies (post_id, user_id, body, body_text) VALUES (%s, %s, %s, %s) RETURNING id",
      (post_id, user_id, cleaned["html"], cleaned["text"]),
    ).fetchone()[0]
    return _get_reply(connection, reply_id, user_id)


def compose_reply_email(from_address: str, reply_id: int) -> EmailMessage | None:
  """The email telling a post's author about a new reply, or None when none should go: the post does not ask for
  it, the author replied to their own post, the author's address is not confirmed, or the reply is gone."""
  with connect() as connection:
    row = connection.execute(
      f"""
      SELECT posts.title, posts.reply_email_token, authors.email, {_AUTHOR}, conversation_replies.body_text, authors.id
      FROM conversation_replies
      JOIN users ON users.id = conversation_replies.user_id
      JOIN conversation_posts posts ON posts.id = conversation_replies.post_id
      JOIN users authors ON authors.id = posts.user_id
      WHERE conversation_replies.id = %s AND posts.email_replies AND posts.reply_email_token IS NOT NULL
        AND posts.user_id <> conversation_replies.user_id AND authors.email_verified_at IS NOT NULL
      """,
      (reply_id,),
    ).fetchone()
  if row is None:
    return None
  post_title, token, address, replier, text, _ = row
  site = site_link("").rstrip("?").rstrip("/")
  email = EmailMessage()
  email["Subject"] = f"New reply to your post “{post_title}”"
  email["From"] = from_address
  email["To"] = address
  one_click = f"{site}/api/subscriptions/unsubscribe?token={token}"
  email["List-Unsubscribe"] = f"<{one_click}>"
  email["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
  email.set_content(
    "\n".join(
      [
        f"{replier} replied to your post “{post_title}” in Conversations:",
        "",
        text.strip(),
        "",
        f"Read it and reply: {site}/conversations",
        "",
        "--",
        f"Sent by {get_public_settings()['title']}: {site}/",
        f"To stop emails about replies to this post, open: {site_link('unsubscribe=' + token)}",
        "(or edit the post and untick “Email me replies”).",
      ]
    )
    + "\n"
  )
  return email


def send_reply_email(reply_id: int) -> None:
  """Emails a new reply to its post's author, if they asked. Run after the reply is saved and answered; a failure
  is logged (never the address or text) and goes no further."""
  try:
    # Ask first whether one should go (a reply needs none most of the time), then fetch the mail settings.
    if compose_reply_email("", reply_id) is None:
      return
    settings = load_mail_settings()
    email = compose_reply_email(settings["from_address"], reply_id)
    if email is not None:
      send_email(settings, email)
  except Exception as problem:
    logger.error("Reply email for reply %s not sent: %s: %s", reply_id, type(problem).__name__, problem if isinstance(problem, MailUnavailable) else "")
  _text_reply(reply_id)


def _text_reply(reply_id: int) -> None:
  """The reply as a short text too, if the post's author asked for replies and for texts (sms.py)."""
  with connect() as connection:
    row = connection.execute(
      f"""
      SELECT posts.user_id, posts.title, {_AUTHOR}, conversation_replies.body_text
      FROM conversation_replies
      JOIN users ON users.id = conversation_replies.user_id
      JOIN conversation_posts posts ON posts.id = conversation_replies.post_id
      WHERE conversation_replies.id = %s AND posts.email_replies AND posts.user_id <> conversation_replies.user_id
      """,
      (reply_id,),
    ).fetchone()
  if row:
    author_id, post_title, replier, text = row
    sms.text_user(author_id, f"{replier} replied to “{post_title}”: {text}", sms.site_address("/conversations"))


def update_reply(user_id: int, reply_id: int, body: str) -> dict:
  """Replaces the text of one of the member's own replies."""
  cleaned = _cleaned(body, REPLY_HTML_LIMIT, REPLY_TEXT_LIMIT, "reply")
  with connect() as connection:
    row = connection.execute(
      "UPDATE conversation_replies SET body = %s, body_text = %s, updated_at = now() WHERE id = %s AND user_id = %s RETURNING id",
      (cleaned["html"], cleaned["text"], reply_id, user_id),
    ).fetchone()
    if row is None:
      raise ConversationProblem("That reply was not found.", 404)
    return _get_reply(connection, reply_id, user_id)


def delete_reply(user_id: int, reply_id: int) -> None:
  with connect() as connection:
    deleted = connection.execute(
      "DELETE FROM conversation_replies WHERE id = %s AND user_id = %s RETURNING id", (reply_id, user_id)
    ).fetchone()
  if deleted is None:
    raise ConversationProblem("That reply was not found.", 404)


# For the Drupal "Conversations" admin page (scripts/manage_conversations.py): an administrator sees every
# post and reply with its author's address, and can delete any of them.
ADMIN_PER_PAGE = 50
EXCERPT_LENGTH = 200


def _excerpt(text: str) -> str:
  return text if len(text) <= EXCERPT_LENGTH else text[:EXCERPT_LENGTH].rstrip() + "…"


def _admin_post(row) -> dict:
  return {
    "id": row[0],
    "title": row[1],
    "body": row[2],
    "excerpt": _excerpt(row[3]),
    "created_at": row[4].isoformat(),
    "updated_at": row[5].isoformat(),
    "author": row[6],
    "author_email": row[7],
    "reply_count": row[8],
    "board": row[9],
    "is_anonymous": row[10],
    "is_private": row[11],
    "email_to_prayer_list": row[12],
    "answered_at": row[13].isoformat() if row[13] else None,
  }


_ADMIN_COLUMNS = f"""
  conversation_posts.id, conversation_posts.title, conversation_posts.body, conversation_posts.body_text,
  conversation_posts.created_at, conversation_posts.updated_at, {_AUTHOR}, users.email,
  (SELECT count(*) FROM conversation_replies WHERE conversation_replies.post_id = conversation_posts.id),
  conversation_posts.board, conversation_posts.is_anonymous, conversation_posts.is_private,
  conversation_posts.email_to_prayer_list, conversation_posts.answered_at
"""
_ADMIN_REPLY_COLUMNS = f"""
  conversation_replies.id, conversation_replies.post_id, conversation_replies.body, conversation_replies.body_text,
  conversation_replies.created_at, conversation_replies.updated_at, {_AUTHOR}, users.email,
  (SELECT title FROM conversation_posts WHERE conversation_posts.id = conversation_replies.post_id)
"""


def _admin_reply(row) -> dict:
  return {
    "id": row[0],
    "post_id": row[1],
    "body": row[2],
    "excerpt": _excerpt(row[3]),
    "created_at": row[4].isoformat(),
    "updated_at": row[5].isoformat(),
    "author": row[6],
    "author_email": row[7],
    "post_title": row[8],
  }


def admin_list_posts(query: str = "", page: int = 1, board: str = "") -> dict:
  """Every post, newest first, ADMIN_PER_PAGE at a time; query keeps those with every word in the title, the
  text, the author's name or address, or a reply; board (when given) those of one board."""
  page = max(page, 1)
  conditions, values = _search_conditions(query.split()[:QUERY_WORD_LIMIT], include_email=True)
  if board:
    conditions.append("conversation_posts.board = %(board)s")
    values["board"] = _checked_board(board)
  where = " AND ".join(conditions) or "true"
  with connect() as connection:
    total = connection.execute(f"SELECT count(*) FROM {_FROM} WHERE {where}", values).fetchone()[0]
    rows = connection.execute(
      f"""
      SELECT {_ADMIN_COLUMNS} FROM {_FROM} WHERE {where}
      ORDER BY conversation_posts.created_at DESC, conversation_posts.id DESC LIMIT %(limit)s OFFSET %(offset)s
      """,
      {**values, "limit": ADMIN_PER_PAGE, "offset": (page - 1) * ADMIN_PER_PAGE},
    ).fetchall()
  return {"posts": [_admin_post(row) for row in rows], "total": total, "page": page, "per_page": ADMIN_PER_PAGE}


def admin_get_post(post_id: int) -> dict:
  """One post with its replies, oldest first, each with its author's address."""
  with connect() as connection:
    row = connection.execute(f"SELECT {_ADMIN_COLUMNS} FROM {_FROM} WHERE conversation_posts.id = %s", (post_id,)).fetchone()
    if row is None:
      raise ConversationProblem("There is no such post. It may have been deleted.", 404)
    replies = connection.execute(
      f"""
      SELECT {_ADMIN_REPLY_COLUMNS} FROM {_REPLY_FROM} WHERE conversation_replies.post_id = %s
      ORDER BY conversation_replies.created_at, conversation_replies.id
      """,
      (post_id,),
    ).fetchall()
  return {**_admin_post(row), "replies": [_admin_reply(reply) for reply in replies]}


def admin_delete_post(post_id: int) -> dict:
  """Deletes any member's post with its replies (an administrator removing it). Returns what was deleted."""
  post = admin_get_post(post_id)
  with connect() as connection:
    connection.execute("DELETE FROM conversation_posts WHERE id = %s", (post_id,))
  return post


def admin_get_reply(reply_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(
      f"SELECT {_ADMIN_REPLY_COLUMNS} FROM {_REPLY_FROM} WHERE conversation_replies.id = %s", (reply_id,)
    ).fetchone()
  if row is None:
    raise ConversationProblem("There is no such reply. It may have been deleted.", 404)
  return _admin_reply(row)


def admin_delete_reply(reply_id: int) -> dict:
  """Deletes any member's reply (an administrator removing it). Returns what was deleted."""
  reply = admin_get_reply(reply_id)
  with connect() as connection:
    connection.execute("DELETE FROM conversation_replies WHERE id = %s", (reply_id,))
  return reply
