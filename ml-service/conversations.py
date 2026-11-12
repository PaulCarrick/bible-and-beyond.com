"""Conversations: a blog of posts written by members of the main site.

Only accounts an administrator allowed (users.use_conversations) may use it; main.py checks that on every
endpoint. Every allowed member reads every post (there are no private posts); only a post's author can change
or delete it, and anyone else is told it was not found, as with notes. A post has a title and a body: a little
HTML from the editor (Quill), cleaned before it is kept (contact.check_rich_text), so it is safe to show.
"""

from contact import ContactProblem, check_rich_text
from search import connect

TITLE_LIMIT = 200
POST_TEXT_LIMIT = 20000
POST_HTML_LIMIT = 120000
# Plenty for any member; it stops one account from filling the database.
MAX_POSTS_PER_USER = 1000
PER_PAGE_LIMIT = 50
QUERY_WORD_LIMIT = 10

# The author's name is read with the post, so a changed name shows on every post. An account with no name
# shows as "A member": the email address is never shown to other members.
_COLUMNS = """
  conversation_posts.id, conversation_posts.user_id, conversation_posts.title, conversation_posts.body,
  conversation_posts.created_at, conversation_posts.updated_at,
  COALESCE(NULLIF(concat_ws(' ', users.first_name, users.last_name), ''), 'A member')
"""
_FROM = "conversation_posts JOIN users ON users.id = conversation_posts.user_id"


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
  }


def _checked(title: str, body: str) -> tuple[str, dict]:
  title = " ".join((title or "").split())
  if not title:
    raise ConversationProblem("Please give the post a title.")
  if len(title) > TITLE_LIMIT:
    raise ConversationProblem(f"The title can be up to {TITLE_LIMIT} characters.")
  try:
    cleaned = check_rich_text(body, POST_HTML_LIMIT, POST_TEXT_LIMIT, "post")
  except ContactProblem as problem:
    raise ConversationProblem(str(problem)) from problem
  return title, cleaned


def _get(connection, post_id: int, viewer_id: int) -> dict:
  row = connection.execute(f"SELECT {_COLUMNS} FROM {_FROM} WHERE conversation_posts.id = %s", (post_id,)).fetchone()
  return _row_to_post(row, viewer_id)


def create_post(user_id: int, title: str, body: str) -> dict:
  title, cleaned = _checked(title, body)
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


def list_posts(viewer_id: int, query: str | None = None, only_mine: bool = False, page: int = 1, per_page: int = 10) -> dict:
  """Every member's posts, newest first, one page of them: {"posts", "total", "page", "per_page"}.

  query keeps the posts that have every word of it, in any case and any part of a word, in the title, the
  text or the author's name. only_mine keeps the viewer's own posts."""
  if page < 1 or not 1 <= per_page <= PER_PAGE_LIMIT:
    raise ConversationProblem(f"Pages are from 1 to {PER_PAGE_LIMIT} posts.")
  conditions = ["true"]
  values: list = []
  if only_mine:
    conditions.append("conversation_posts.user_id = %s")
    values.append(viewer_id)
  words = (query or "").split()
  if len(words) > QUERY_WORD_LIMIT:
    raise ConversationProblem(f"Please search for up to {QUERY_WORD_LIMIT} words.")
  for word in words:
    conditions.append(
      "(conversation_posts.title ILIKE %s OR conversation_posts.body_text ILIKE %s"
      " OR concat_ws(' ', users.first_name, users.last_name) ILIKE %s)"
    )
    values.extend([_like_pattern(word)] * 3)
  where = " AND ".join(conditions)
  with connect() as connection:
    total = connection.execute(f"SELECT count(*) FROM {_FROM} WHERE {where}", values).fetchone()[0]
    rows = connection.execute(
      f"""
      SELECT {_COLUMNS} FROM {_FROM} WHERE {where}
      ORDER BY conversation_posts.created_at DESC, conversation_posts.id DESC LIMIT %s OFFSET %s
      """,
      [*values, per_page, (page - 1) * per_page],
    ).fetchall()
  return {"posts": [_row_to_post(row, viewer_id) for row in rows], "total": total, "page": page, "per_page": per_page}


def update_post(user_id: int, post_id: int, title: str, body: str) -> dict:
  """Replaces the title and text of one of the member's own posts."""
  title, cleaned = _checked(title, body)
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
  with connect() as connection:
    deleted = connection.execute(
      "DELETE FROM conversation_posts WHERE id = %s AND user_id = %s RETURNING id", (post_id, user_id)
    ).fetchone()
  if deleted is None:
    raise ConversationProblem("That post was not found.", 404)


# For the Drupal "Conversations" admin page (scripts/manage_conversations.py): an administrator sees every
# post with its author's address, and can delete any of them.
ADMIN_PER_PAGE = 50
EXCERPT_LENGTH = 200


def _admin_post(row) -> dict:
  text = row[3]
  return {
    "id": row[0],
    "title": row[1],
    "body": row[2],
    "excerpt": text if len(text) <= EXCERPT_LENGTH else text[:EXCERPT_LENGTH].rstrip() + "…",
    "created_at": row[4].isoformat(),
    "updated_at": row[5].isoformat(),
    "author": row[6],
    "author_email": row[7],
  }


_ADMIN_COLUMNS = """
  conversation_posts.id, conversation_posts.title, conversation_posts.body, conversation_posts.body_text,
  conversation_posts.created_at, conversation_posts.updated_at,
  COALESCE(NULLIF(concat_ws(' ', users.first_name, users.last_name), ''), 'A member'), users.email
"""


def admin_list_posts(query: str = "", page: int = 1) -> dict:
  """Every post, newest first, ADMIN_PER_PAGE at a time; query keeps those with every word in the title, the
  text, the author's name or address."""
  page = max(page, 1)
  conditions = ["true"]
  values: list = []
  for word in query.split()[:QUERY_WORD_LIMIT]:
    conditions.append(
      "(conversation_posts.title ILIKE %s OR conversation_posts.body_text ILIKE %s"
      " OR concat_ws(' ', users.first_name, users.last_name) ILIKE %s OR users.email ILIKE %s)"
    )
    values.extend([_like_pattern(word)] * 4)
  where = " AND ".join(conditions)
  with connect() as connection:
    total = connection.execute(f"SELECT count(*) FROM {_FROM} WHERE {where}", values).fetchone()[0]
    rows = connection.execute(
      f"""
      SELECT {_ADMIN_COLUMNS} FROM {_FROM} WHERE {where}
      ORDER BY conversation_posts.created_at DESC, conversation_posts.id DESC LIMIT %s OFFSET %s
      """,
      [*values, ADMIN_PER_PAGE, (page - 1) * ADMIN_PER_PAGE],
    ).fetchall()
  return {"posts": [_admin_post(row) for row in rows], "total": total, "page": page, "per_page": ADMIN_PER_PAGE}


def admin_get_post(post_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {_ADMIN_COLUMNS} FROM {_FROM} WHERE conversation_posts.id = %s", (post_id,)).fetchone()
  if row is None:
    raise ConversationProblem("There is no such post. It may have been deleted.", 404)
  return _admin_post(row)


def admin_delete_post(post_id: int) -> dict:
  """Deletes any member's post (an administrator removing it). Returns what was deleted."""
  post = admin_get_post(post_id)
  with connect() as connection:
    connection.execute("DELETE FROM conversation_posts WHERE id = %s", (post_id,))
  return post
