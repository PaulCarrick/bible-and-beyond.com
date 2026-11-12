"""Conversations: a blog of posts written by members of the main site, with replies.

Only accounts an administrator allowed (users.use_conversations) may use it; main.py checks that on every
endpoint. Every allowed member reads every post and reply (there are no private posts) and may reply to any
post; only the author of a post or reply can change or delete it, and anyone else is told it was not found, as
with notes. Deleting a post deletes its replies. A post has a title and a body, a reply only a body: a little
HTML from the editor (Quill), cleaned before it is kept (contact.check_rich_text), so it is safe to show.
"""

from contact import ContactProblem, check_rich_text
from search import connect

TITLE_LIMIT = 200
POST_TEXT_LIMIT = 20000
POST_HTML_LIMIT = 120000
REPLY_TEXT_LIMIT = 5000
REPLY_HTML_LIMIT = 30000
# Plenty for any member; they stop one account from filling the database.
MAX_POSTS_PER_USER = 1000
MAX_REPLIES_PER_USER = 5000
PER_PAGE_LIMIT = 50
QUERY_WORD_LIMIT = 10

# An author's name is read with the post or reply, so a changed name shows everywhere. An account with no name
# shows as "A member": the email address is never shown to other members.
_AUTHOR = "COALESCE(NULLIF(concat_ws(' ', users.first_name, users.last_name), ''), 'A member')"
_COLUMNS = f"""
  conversation_posts.id, conversation_posts.user_id, conversation_posts.title, conversation_posts.body,
  conversation_posts.created_at, conversation_posts.updated_at, {_AUTHOR}
"""
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
    "author": row[6],
    # Whether the member asking wrote it (the page then offers Edit and Delete).
    "is_mine": row[1] == viewer_id,
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


def _checked_title(title: str) -> str:
  title = " ".join((title or "").split())
  if not title:
    raise ConversationProblem("Please give the post a title.")
  if len(title) > TITLE_LIMIT:
    raise ConversationProblem(f"The title can be up to {TITLE_LIMIT} characters.")
  return title


def _cleaned(body: str, html_limit: int, text_limit: int, what: str) -> dict:
  try:
    return check_rich_text(body, html_limit, text_limit, what)
  except ContactProblem as problem:
    raise ConversationProblem(str(problem)) from problem


def _get(connection, post_id: int, viewer_id: int) -> dict:
  row = connection.execute(f"SELECT {_COLUMNS} FROM {_FROM} WHERE conversation_posts.id = %s", (post_id,)).fetchone()
  return _with_replies(connection, [_row_to_post(row, viewer_id)], viewer_id)[0]


def create_post(user_id: int, title: str, body: str) -> dict:
  title = _checked_title(title)
  cleaned = _cleaned(body, POST_HTML_LIMIT, POST_TEXT_LIMIT, "post")
  with connect() as connection:
    count = connection.execute("SELECT count(*) FROM conversation_posts WHERE user_id = %s", (user_id,)).fetchone()[0]
    if count >= MAX_POSTS_PER_USER:
      raise ConversationProblem(f"You have reached the limit of {MAX_POSTS_PER_USER} posts. Please delete some first.")
    post_id = connection.execute(
      "INSERT INTO conversation_posts (user_id, title, body, body_text) VALUES (%s, %s, %s, %s) RETURNING id",
      (user_id, title, cleaned["html"], cleaned["text"]),
    ).fetchone()[0]
    return _get(connection, post_id, user_id)


def _like_pattern(word: str) -> str:
  """A word as a LIKE pattern that matches it anywhere, with %, _ and the escape itself taken literally."""
  escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
  return f"%{escaped}%"


def _search_conditions(words: list[str], include_email: bool = False) -> tuple[list[str], dict]:
  """One condition per word: the word is in the post's title or text, its author's name (or, for the admin page,
  address) or the text of one of its replies. The values are named, since each word is used several times."""
  conditions = []
  values = {}
  for number, word in enumerate(words):
    name = f"%(word_{number})s"
    values[f"word_{number}"] = _like_pattern(word)
    email = f" OR users.email ILIKE {name}" if include_email else ""
    conditions.append(
      f"""(
        conversation_posts.title ILIKE {name} OR conversation_posts.body_text ILIKE {name}
        OR concat_ws(' ', users.first_name, users.last_name) ILIKE {name}{email}
        OR EXISTS (
          SELECT 1 FROM conversation_replies
          WHERE conversation_replies.post_id = conversation_posts.id AND conversation_replies.body_text ILIKE {name}
        )
      )"""
    )
  return conditions, values


def list_posts(viewer_id: int, query: str | None = None, only_mine: bool = False, page: int = 1, per_page: int = 10) -> dict:
  """Every member's posts with their replies, newest post first, one page of them: {"posts", "total", "page",
  "per_page"}.

  query keeps the posts that have every word of it, in any case and any part of a word, in the title, the
  text, the author's name or a reply. only_mine keeps the viewer's own posts."""
  if page < 1 or not 1 <= per_page <= PER_PAGE_LIMIT:
    raise ConversationProblem(f"Pages are from 1 to {PER_PAGE_LIMIT} posts.")
  words = (query or "").split()
  if len(words) > QUERY_WORD_LIMIT:
    raise ConversationProblem(f"Please search for up to {QUERY_WORD_LIMIT} words.")
  conditions, values = _search_conditions(words)
  if only_mine:
    conditions.append("conversation_posts.user_id = %(viewer)s")
    values["viewer"] = viewer_id
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


def update_post(user_id: int, post_id: int, title: str, body: str) -> dict:
  """Replaces the title and text of one of the member's own posts."""
  title = _checked_title(title)
  cleaned = _cleaned(body, POST_HTML_LIMIT, POST_TEXT_LIMIT, "post")
  with connect() as connection:
    row = connection.execute(
      """
      UPDATE conversation_posts SET title = %s, body = %s, body_text = %s, updated_at = now()
      WHERE id = %s AND user_id = %s RETURNING id
      """,
      (title, cleaned["html"], cleaned["text"], post_id, user_id),
    ).fetchone()
    if row is None:
      raise ConversationProblem("That post was not found.", 404)
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
    if not connection.execute("SELECT 1 FROM conversation_posts WHERE id = %s", (post_id,)).fetchone():
      raise ConversationProblem("That post was not found. It may have been deleted.", 404)
    count = connection.execute("SELECT count(*) FROM conversation_replies WHERE user_id = %s", (user_id,)).fetchone()[0]
    if count >= MAX_REPLIES_PER_USER:
      raise ConversationProblem(f"You have reached the limit of {MAX_REPLIES_PER_USER} replies. Please delete some first.")
    reply_id = connection.execute(
      "INSERT INTO conversation_replies (post_id, user_id, body, body_text) VALUES (%s, %s, %s, %s) RETURNING id",
      (post_id, user_id, cleaned["html"], cleaned["text"]),
    ).fetchone()[0]
    return _get_reply(connection, reply_id, user_id)


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
  }


_ADMIN_COLUMNS = f"""
  conversation_posts.id, conversation_posts.title, conversation_posts.body, conversation_posts.body_text,
  conversation_posts.created_at, conversation_posts.updated_at, {_AUTHOR}, users.email,
  (SELECT count(*) FROM conversation_replies WHERE conversation_replies.post_id = conversation_posts.id)
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


def admin_list_posts(query: str = "", page: int = 1) -> dict:
  """Every post, newest first, ADMIN_PER_PAGE at a time; query keeps those with every word in the title, the
  text, the author's name or address, or a reply."""
  page = max(page, 1)
  conditions, values = _search_conditions(query.split()[:QUERY_WORD_LIMIT], include_email=True)
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
