"""Posts to one member (added 2026-11-23 at the owner's request).

A member writing on the Conversations board may send a post to one member instead of everyone
(conversation_posts.recipient_id). Only the two of them see it, with its replies (and the site's administrators,
on the Drupal page). The first time someone sends to a member, the member is asked first: a request on the
Conversations page and by email or text (their usual choice), with Accept and Decline. Until they answer, the
sender's posts to them are held (the sender sees "waiting"); Accept shows them and every later one, and they are
never asked about that sender again; Decline means the sender cannot send to them. The member can change either
answer on My account. message_permissions (migration 069) keeps one row per sender and recipient.

Private posts are never sent to the AI check (like private prayer requests) and never go to Get Conversation Posts.
"""

import logging
import secrets
from email.message import EmailMessage

import sms
from accounts import site_link
from contact import MailUnavailable, load_mail_settings, send_email
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger(__name__)

# The name shown for a member: first and last name ("A member" without one; never an address).
_NAME = "COALESCE(NULLIF(concat_ws(' ', {table}.first_name, {table}.last_name), ''), 'A member')"
STATUSES = ("pending", "accepted", "declined")


class DirectPostProblem(Exception):
  """The request cannot be done; the text says why and is fit to show the member."""

  def __init__(self, message: str, status_code: int = 422):
    super().__init__(message)
    self.status_code = status_code


def members(viewer_id: int) -> list[dict]:
  """Who a member may send a post to: the other open accounts allowed to use Conversations that have a name, by
  name ({id, name}; never an address)."""
  with connect() as connection:
    rows = connection.execute(
      f"""
      SELECT id, {_NAME.format(table='users')} FROM users
      WHERE use_conversations AND disabled_at IS NULL AND id <> %s
        AND NULLIF(concat_ws(' ', first_name, last_name), '') IS NOT NULL
      ORDER BY lower(concat_ws(' ', first_name, last_name)), id
      """,
      (viewer_id,),
    ).fetchall()
  return [{"id": row[0], "name": row[1]} for row in rows]


def check_recipient(connection, sender_id: int, recipient_id) -> int:
  """The recipient of a new post, checked: another open account allowed Conversations, who has not declined the
  sender. Makes the waiting request the first time. Returns the recipient's id."""
  if isinstance(recipient_id, str) and recipient_id.strip().isdigit():
    recipient_id = int(recipient_id.strip())
  if not isinstance(recipient_id, int) or isinstance(recipient_id, bool):
    raise DirectPostProblem("Choose the member to send it to.")
  if recipient_id == sender_id:
    raise DirectPostProblem("You cannot send a post to yourself.")
  found = connection.execute(
    "SELECT 1 FROM users WHERE id = %s AND use_conversations AND disabled_at IS NULL", (recipient_id,)
  ).fetchone()
  if found is None:
    raise DirectPostProblem("That member was not found, or cannot use Conversations.")
  row = connection.execute(
    "SELECT status FROM message_permissions WHERE sender_id = %s AND recipient_id = %s", (sender_id, recipient_id)
  ).fetchone()
  if row is not None and row[0] == "declined":
    raise DirectPostProblem("That member is not accepting posts from you.", 403)
  if row is None:
    connection.execute(
      "INSERT INTO message_permissions (sender_id, recipient_id, token) VALUES (%s, %s, %s)",
      (sender_id, recipient_id, secrets.token_urlsafe(24)),
    )
  return recipient_id


def status(sender_id: int, recipient_id: int) -> str | None:
  with connect() as connection:
    row = connection.execute(
      "SELECT status FROM message_permissions WHERE sender_id = %s AND recipient_id = %s", (sender_id, recipient_id)
    ).fetchone()
  return row[0] if row else None


# --- the recipient's answers -------------------------------------------------------------------------------


def _describe(row) -> dict:
  return {
    "sender_id": row[0], "sender": row[1], "status": row[2],
    "requested_at": row[3].isoformat(), "answered_at": row[4].isoformat() if row[4] else None,
  }


_COLUMNS = f"p.sender_id, {_NAME.format(table='u')}, p.status, p.requested_at, p.answered_at"


def requests_for(recipient_id: int) -> list[dict]:
  """The member's waiting requests, oldest first."""
  with connect() as connection:
    rows = connection.execute(
      f"""SELECT {_COLUMNS} FROM message_permissions p JOIN users u ON u.id = p.sender_id
      WHERE p.recipient_id = %s AND p.status = 'pending' ORDER BY p.requested_at, p.sender_id""",
      (recipient_id,),
    ).fetchall()
  return [_describe(row) for row in rows]


def permissions_for(recipient_id: int) -> list[dict]:
  """Everyone who has asked to send the member posts, with the answer (My account), by name."""
  with connect() as connection:
    rows = connection.execute(
      f"""SELECT {_COLUMNS} FROM message_permissions p JOIN users u ON u.id = p.sender_id
      WHERE p.recipient_id = %s ORDER BY lower({_NAME.format(table='u')}), p.sender_id""",
      (recipient_id,),
    ).fetchall()
  return [_describe(row) for row in rows]


def answer(recipient_id: int, sender_id: int, accept: bool) -> dict:
  """Accepts or declines a sender (or changes the answer later). Accepting shows the posts held until now."""
  with connect() as connection:
    row = connection.execute(
      f"""UPDATE message_permissions p SET status = %s, answered_at = now()
      FROM users u WHERE u.id = p.sender_id AND p.sender_id = %s AND p.recipient_id = %s
      RETURNING {_COLUMNS}""",
      ("accepted" if accept else "declined", sender_id, recipient_id),
    ).fetchone()
  if row is None:
    raise DirectPostProblem("That request was not found.", 404)
  return _describe(row)


def request_by_token(token: str) -> dict:
  """The request a link in an email or text answers: who asked, to whom (first name only) and its answer."""
  with connect() as connection:
    row = connection.execute(
      f"""SELECT {_COLUMNS}, COALESCE(r.first_name, '') FROM message_permissions p
      JOIN users u ON u.id = p.sender_id JOIN users r ON r.id = p.recipient_id
      WHERE p.token = %s AND r.disabled_at IS NULL""",
      (token or "",),
    ).fetchone()
  if row is None:
    raise DirectPostProblem("This link is not valid. It may be old, or the account was closed.", 404)
  return {**_describe(row[:5]), "recipient_first_name": row[5]}


def answer_by_token(token: str, accept: bool) -> dict:
  with connect() as connection:
    row = connection.execute(
      "SELECT p.recipient_id, p.sender_id FROM message_permissions p JOIN users r ON r.id = p.recipient_id "
      "WHERE p.token = %s AND r.disabled_at IS NULL",
      (token or "",),
    ).fetchone()
  if row is None:
    raise DirectPostProblem("This link is not valid. It may be old, or the account was closed.", 404)
  return answer(row[0], row[1], accept)


# --- the emails and texts ----------------------------------------------------------------------------------


def _deliver(recipient_id: int, subject: str, lines: list[str], words: str, link: str) -> None:
  """An email (to a confirmed address) or a text, or both, as the member chose (sms.deliver). Raises when nothing
  reached them, so the caller can try again later."""

  def send_the_email():
    with connect() as connection:
      row = connection.execute(
        "SELECT email FROM users WHERE id = %s AND email IS NOT NULL AND email_verified_at IS NOT NULL AND disabled_at IS NULL",
        (recipient_id,),
      ).fetchone()
    if row is None:
      raise MailUnavailable("The member's address is not confirmed.")
    settings = load_mail_settings()
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = settings["from_address"]
    email["To"] = row[0]
    site = site_link("").rstrip("?").rstrip("/")
    email.set_content("\n".join([*lines, "", "--", f"Sent by {get_public_settings()['title']}: {site}/"]) + "\n")
    send_email(settings, email)

  sms.deliver(recipient_id, send_the_email, words, link)


def _sender_name(connection, user_id: int) -> str:
  return connection.execute(f"SELECT {_NAME.format(table='users')} FROM users WHERE id = %s", (user_id,)).fetchone()[0]


def notify_post(post_id: int) -> str | None:
  """After a post to one member is saved (a background task): the first time, the request (once); once accepted,
  a note that a post arrived. Returns what was sent ("request", "post") or None. A failure is logged and a request
  is tried again with the sender's next post."""
  try:
    with connect() as connection:
      row = connection.execute(
        """SELECT p.user_id, p.recipient_id, p.title, mp.status, mp.token, mp.notified_at IS NULL
        FROM conversation_posts p JOIN message_permissions mp ON mp.sender_id = p.user_id AND mp.recipient_id = p.recipient_id
        WHERE p.id = %s""",
        (post_id,),
      ).fetchone()
      if row is None:
        return None
      sender_id, recipient_id, title, state, token, not_yet = row
      sender = _sender_name(connection, sender_id)
      if state == "pending":
        if not not_yet:
          return None
        # Claimed before sending, so it goes once.
        claimed = connection.execute(
          "UPDATE message_permissions SET notified_at = now() WHERE sender_id = %s AND recipient_id = %s AND notified_at IS NULL RETURNING 1",
          (sender_id, recipient_id),
        ).fetchone()
        if claimed is None:
          return None
    if state == "pending":
      link = site_link("message-request=" + token)
      try:
        _deliver(
          recipient_id,
          f"{sender} would like to send you posts",
          [
            f"{sender} would like to send you private posts in Conversations on {get_public_settings()['title']}.",
            "Only the two of you would see them. Nothing they wrote is shown until you accept.",
            "",
            f"Accept or decline: {link}",
            "",
            "If you accept, you will not be asked again about them. If you decline, they cannot send you posts.",
            "You can change your answer later on the My account page.",
          ],
          f"{sender} would like to send you private posts in Conversations. Accept or decline:",
          link,
        )
      except Exception as problem:
        with connect() as connection:
          connection.execute(
            "UPDATE message_permissions SET notified_at = NULL WHERE sender_id = %s AND recipient_id = %s", (sender_id, recipient_id)
          )
        logger.error("Post request for post %s not sent: %s", post_id, type(problem).__name__)
        return None
      return "request"
    if state == "accepted":
      link = sms.site_address("/conversations")
      _deliver(
        recipient_id,
        f"New post from {sender}: “{title}”",
        [f"{sender} sent you a post in Conversations:", "", title, "", f"Read it and reply: {link}",
         "", "To stop posts from them, use Block on your My account page."],
        f"{sender} sent you a post in Conversations: {title}",
        link,
      )
      return "post"
  except Exception as problem:
    logger.error("Notice for post %s not sent: %s", post_id, type(problem).__name__)
  return None


def notify_reply(reply_id: int) -> bool:
  """After a reply on a post to one member (a background task): the other of the two is told. Not while the
  request waits or after a decline. Returns whether something went."""
  try:
    with connect() as connection:
      row = connection.execute(
        """SELECT r.user_id, p.user_id, p.recipient_id, p.title, r.body_text, mp.status
        FROM conversation_replies r JOIN conversation_posts p ON p.id = r.post_id
        JOIN message_permissions mp ON mp.sender_id = p.user_id AND mp.recipient_id = p.recipient_id
        WHERE r.id = %s AND p.recipient_id IS NOT NULL""",
        (reply_id,),
      ).fetchone()
      if row is None or row[5] != "accepted":
        return False
      replier_id, author_id, recipient_id, title, text, _ = row
      other = recipient_id if replier_id == author_id else author_id
      replier = _sender_name(connection, replier_id)
    link = sms.site_address("/conversations")
    _deliver(
      other,
      f"New reply from {replier}: “{title}”",
      [f"{replier} replied to “{title}” in Conversations:", "", text.strip(), "", f"Read it and reply: {link}"],
      f"{replier} replied to “{title}”: {text}",
      link,
    )
    return True
  except Exception as problem:
    logger.error("Notice for reply %s not sent: %s", reply_id, type(problem).__name__)
    return False
