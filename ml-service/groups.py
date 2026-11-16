"""Groups (added 2026-11-16 at the owner's request, a deacon: "a page called groups that permits me to add, edit
and remove users, permits me to email/sms a message to all members (based on their preferences; no image), send
them a bible verse card (with image) or a message with one of the image backgrounds (randomly selected)").

The Drupal "Groups" page runs scripts/manage_groups.py, which calls this. A group belongs to the Drupal user who
made it (owner_uid; Drupal decides who may see which: a Group leader only their own, a Website administrator all).

Members are added by email address:
- an address with a site account makes an **account member**: they get the group's messages the way they chose
  on My account (email, text or both; texts only if they agreed to them, sms.deliver), once their address is
  confirmed;
- any other address makes a **contact**, with the name (and a phone, for the leader's reference) typed in: they
  get email only, since nobody has their agreement to texts.

Three kinds of message go to every member who has not stopped them:
- **message**: a subject and words; by email and text as above, no picture;
- **verse**: a random well-known verse as a picture card (message_cards.py), previewed first (preview_verse) and
  sent as previewed: the picture in the email (the verse a link to it on the site) and as a picture text (MMS);
- **picture**: the leader's own words written over a random verse a day picture, previewed first
  (preview_picture), sent the same way.

Every email has the leader's address as Reply-To, so replies go to them, and a stop link (and one-click header)
that stops that member's messages from that group only (the devotionals' unsubscribe endpoint handles it).
**No member's address is ever shown** (the owner's request, 2026-11-16: "the recipients of all emails should be
on the bcc ... the leader can be the visible send to"): each email's To is the leader (the site's own address
if the leader has none) and the member is only its hidden recipient (send_email's recipients, the SMTP envelope;
there is no Bcc header to leak). Each member still gets their own copy, so their stop link is theirs alone. The
leader gets one copy of each send, marked as theirs, with how many it went to. What
was sent is kept in group_messages with counts, never with the addresses.
"""

import logging
import random
import re
import secrets
import time
from email.message import EmailMessage

import day_cards
import message_cards
import sms
import verse_a_day
from accounts import AccountProblem, normalize_email, site_link
from contact import CONTROL_CHARACTERS, MailUnavailable, load_mail_settings, send_email
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger("groups")

NAME_LIMIT = 200
DESCRIPTION_LIMIT = 2_000
SUBJECT_LIMIT = 200
MESSAGE_LIMIT = 5_000
# Words on a picture message: more would be too small to read.
PICTURE_TEXT_LIMIT = 400
MAX_MEMBERS = 500
PAUSE_BETWEEN_MEMBERS = 0.5
KINDS = ("message", "verse", "picture")


class GroupProblem(Exception):
  """A group cannot be saved or a message sent; the text says why and is fit to show the leader."""


def _one_line(value: str, label: str, limit: int, required: bool = True) -> str:
  value = " ".join((value or "").split())
  if required and not value:
    raise GroupProblem(f"The {label} is needed.")
  if CONTROL_CHARACTERS.search(value):
    raise GroupProblem(f"The {label} must be plain text on one line.")
  return value[:limit]


def _text(value: str, label: str, limit: int) -> str:
  value = (value or "").replace("\r\n", "\n").strip()
  if not value:
    raise GroupProblem(f"The {label} is needed.")
  if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
    raise GroupProblem(f"The {label} has characters that cannot be sent.")
  if len(value) > limit:
    raise GroupProblem(f"The {label} can be at most {limit:,} characters.")
  return value


# --- groups ------------------------------------------------------------------------------------------------


def _describe_group(row) -> dict:
  return {
    "id": row[0], "name": row[1], "description": row[2], "owner_uid": row[3], "owner_name": row[4],
    "owner_email": row[5], "created_at": row[6].isoformat(), "member_count": row[7], "last_sent_at": row[8].isoformat() if row[8] else None,
  }


GROUP_COLUMNS = """
  g.id, g.name, g.description, g.owner_uid, g.owner_name, g.owner_email, g.created_at,
  (SELECT count(*) FROM group_members m WHERE m.group_id = g.id),
  (SELECT max(sent_at) FROM group_messages s WHERE s.group_id = g.id)
"""


def list_groups(owner_uid: int | None = None) -> list[dict]:
  """The groups by name: one leader's (owner_uid), or all."""
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {GROUP_COLUMNS} FROM member_groups g WHERE %(owner)s::int IS NULL OR g.owner_uid = %(owner)s ORDER BY lower(g.name), g.id",
      {"owner": owner_uid},
    ).fetchall()
  return [_describe_group(row) for row in rows]


def get_group(group_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {GROUP_COLUMNS} FROM member_groups g WHERE g.id = %s", (group_id,)).fetchone()
  if row is None:
    raise GroupProblem("That group does not exist (it may have been deleted).")
  group = _describe_group(row)
  group["members"] = list_members(group_id)
  return group


def save_group(
  group_id: int | None, details: dict, owner_uid: int, owner_name: str, owner_email: str, set_owner: bool = False
) -> dict:
  """Makes a group (group_id None) or changes its name and description. The owner is set when it is made, and
  their name and address (the Reply-To of its emails) are brought up to date on every change. With set_owner
  (an administrator choosing another leader; Drupal checks who may) the group moves to the owner given."""
  name = _one_line(details.get("name", ""), "group's name", NAME_LIMIT)
  description = (details.get("description") or "").strip()[:DESCRIPTION_LIMIT]
  with connect() as connection:
    if group_id is None:
      group_id = connection.execute(
        "INSERT INTO member_groups (name, description, owner_uid, owner_name, owner_email) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (name, description, owner_uid, owner_name, owner_email),
      ).fetchone()[0]
    else:
      changed = connection.execute(
        """
        UPDATE member_groups SET name = %s, description = %s,
          owner_name = CASE WHEN owner_uid = %s THEN %s ELSE owner_name END,
          owner_email = CASE WHEN owner_uid = %s THEN %s ELSE owner_email END
        WHERE id = %s RETURNING id
        """,
        (name, description, owner_uid, owner_name, owner_uid, owner_email, group_id),
      ).fetchone()
      if changed is None:
        raise GroupProblem("That group does not exist (it may have been deleted).")
      if set_owner:
        connection.execute(
          "UPDATE member_groups SET owner_uid = %s, owner_name = %s, owner_email = %s WHERE id = %s",
          (owner_uid, owner_name, owner_email, group_id),
        )
  return get_group(group_id)


def delete_group(group_id: int) -> dict:
  """Deletes a group with its members (not their site accounts) and its record of messages."""
  group = get_group(group_id)
  with connect() as connection:
    connection.execute("DELETE FROM member_groups WHERE id = %s", (group_id,))
  return group


# --- members -----------------------------------------------------------------------------------------------

MEMBER_COLUMNS = """
  m.id, m.user_id, m.stopped_at,
  CASE WHEN m.user_id IS NULL THEN m.name
       ELSE COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), m.name, '') END,
  COALESCE(u.email, m.email), CASE WHEN m.user_id IS NULL THEN m.phone ELSE COALESCE(u.phone, '') END,
  u.email_verified_at IS NOT NULL
"""


def _how(connection, user_id: int | None, verified: bool, stopped: bool) -> str:
  """How the group's messages reach a member, in words for the leader."""
  if stopped:
    return "Stopped (they followed the stop link in an email)"
  if user_id is None:
    return "Email"
  if not verified:
    return "Nothing until they confirm their email address"
  by_email, number = sms.delivery_for_user(connection, user_id)
  return "Email and text" if by_email and number else ("Text" if number else "Email")


def list_members(group_id: int) -> list[dict]:
  with connect() as connection:
    rows = connection.execute(
      f"""
      SELECT {MEMBER_COLUMNS} FROM group_members m LEFT JOIN users u ON u.id = m.user_id
      WHERE m.group_id = %s ORDER BY lower(COALESCE(NULLIF(m.name, ''), u.first_name, u.email, m.email)), m.id
      """,
      (group_id,),
    ).fetchall()
    return [
      {
        "id": row[0], "is_account": row[1] is not None, "stopped": row[2] is not None, "name": row[3],
        "email": row[4], "phone": row[5], "receives": _how(connection, row[1], row[6], row[2] is not None),
      }
      for row in rows
    ]


def _member_details(details: dict) -> tuple[str, str, str]:
  try:
    email = normalize_email(details.get("email", ""))
  except AccountProblem as problem:
    raise GroupProblem(str(problem)) from problem
  name = _one_line(details.get("name", ""), "name", NAME_LIMIT, required=False)
  phone = sms.format_phone(_one_line(details.get("phone", ""), "phone number", 40, required=False))
  return email, name, phone


def add_member(group_id: int, details: dict) -> dict:
  """Adds a member by email address: the site account with that address, else a contact with the name given."""
  get_group(group_id)
  email, name, phone = _member_details(details)
  with connect() as connection:
    if connection.execute("SELECT count(*) FROM group_members WHERE group_id = %s", (group_id,)).fetchone()[0] >= MAX_MEMBERS:
      raise GroupProblem(f"A group can have at most {MAX_MEMBERS} members.")
    account = connection.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
    taken = connection.execute(
      "SELECT 1 FROM group_members WHERE group_id = %s AND (user_id = %s OR lower(email) = %s)",
      (group_id, account[0] if account else None, email),
    ).fetchone()
    if taken:
      raise GroupProblem("That person is already in the group.")
    if account is None and not name:
      raise GroupProblem("That address has no account on the site, so type the person's name too.")
    member_id = connection.execute(
      """
      INSERT INTO group_members (group_id, user_id, name, email, phone, stop_token)
      VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
      """,
      (group_id, account[0] if account else None, name, None if account else email, "" if account else phone, secrets.token_urlsafe(24)),
    ).fetchone()[0]
  return next(member for member in list_members(group_id) if member["id"] == member_id)


def list_candidates(group_id: int) -> list[dict]:
  """The site's accounts that are not in the group yet, by name (the Add a member list; the owner's request,
  2026-11-16: "an easy way of adding site users from a multi-select list")."""
  get_group(group_id)
  with connect() as connection:
    rows = connection.execute(
      """
      SELECT u.id, COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), ''), u.email,
             u.email_verified_at IS NOT NULL
      FROM users u
      WHERE NOT EXISTS (SELECT 1 FROM group_members m WHERE m.group_id = %s AND m.user_id = u.id)
      ORDER BY lower(COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), u.email)), u.id
      """,
      (group_id,),
    ).fetchall()
  return [{"id": row[0], "name": row[1], "email": row[2], "confirmed": row[3]} for row in rows]


def add_accounts(group_id: int, user_ids: list) -> list[dict]:
  """Adds site accounts by their ids (ticked in the list). One already in the group, or no longer on the site,
  is passed over. Returns the members added."""
  get_group(group_id)
  try:
    wanted = sorted({int(user_id) for user_id in user_ids})
  except (TypeError, ValueError):
    raise GroupProblem("Please tick the people to add.")
  if not wanted:
    raise GroupProblem("Please tick the people to add.")
  added = []
  with connect() as connection:
    present = connection.execute("SELECT count(*) FROM group_members WHERE group_id = %s", (group_id,)).fetchone()[0]
    if present + len(wanted) > MAX_MEMBERS:
      raise GroupProblem(f"A group can have at most {MAX_MEMBERS} members.")
    for user_id in wanted:
      row = connection.execute(
        """
        INSERT INTO group_members (group_id, user_id, stop_token)
        SELECT %s, id, %s FROM users WHERE id = %s
          AND NOT EXISTS (SELECT 1 FROM group_members WHERE group_id = %s AND user_id = %s)
        RETURNING id
        """,
        (group_id, secrets.token_urlsafe(24), user_id, group_id, user_id),
      ).fetchone()
      if row:
        added.append(row[0])
  return [member for member in list_members(group_id) if member["id"] in added]


def update_member(group_id: int, member_id: int, details: dict) -> dict:
  """Changes a contact's name, address and phone. An account member's details are their own (My account)."""
  with connect() as connection:
    row = connection.execute("SELECT user_id FROM group_members WHERE id = %s AND group_id = %s", (member_id, group_id)).fetchone()
  if row is None:
    raise GroupProblem("That member is not in the group (they may have been removed).")
  if row[0] is not None:
    raise GroupProblem("This member has an account on the site; they change their own details on My account.")
  email, name, phone = _member_details(details)
  if not name:
    raise GroupProblem("The name is needed.")
  with connect() as connection:
    if connection.execute(
      "SELECT 1 FROM group_members WHERE group_id = %s AND lower(email) = %s AND id <> %s", (group_id, email, member_id)
    ).fetchone():
      raise GroupProblem("Another member of the group has that address.")
    connection.execute("UPDATE group_members SET name = %s, email = %s, phone = %s WHERE id = %s", (name, email, phone, member_id))
  return next(member for member in list_members(group_id) if member["id"] == member_id)


def remove_member(group_id: int, member_id: int) -> dict:
  found = [member for member in list_members(group_id) if member["id"] == member_id]
  if not found:
    raise GroupProblem("That member is not in the group (they may have been removed).")
  with connect() as connection:
    connection.execute("DELETE FROM group_members WHERE id = %s AND group_id = %s", (member_id, group_id))
  return found[0]


def stop_with_token(connection, token: str) -> str | None:
  """The stop link of a group email: that member gets no more messages from that group. Returns the group's
  name, or None when the token is not a group's."""
  row = connection.execute(
    """
    UPDATE group_members SET stopped_at = COALESCE(stopped_at, now()) WHERE stop_token = %s
    RETURNING (SELECT name FROM member_groups WHERE id = group_members.group_id)
    """,
    (token,),
  ).fetchone()
  return row[0] if row else None


# --- previews ----------------------------------------------------------------------------------------------


def preview_verse(chooser=random) -> dict:
  """A random well-known verse as a card, saved so the same card can be sent (send with its card and verse)."""
  with connect() as connection:
    verse = verse_a_day.pick_verse(connection, list(day_cards._pool()), chooser=chooser)
  if verse is None:
    raise GroupProblem("There is no Bible to choose a verse from.")
  caption = f"{verse['reference']} ({verse['translation']})"
  card = message_cards.make_card(verse["text"], caption, plain_if_none=True)
  if card is None:
    raise GroupProblem("The picture could not be made; try again.")
  return {
    "card": card.path.name, "image": message_cards.data_address(card), "words": verse["text"], "caption": caption,
    "verse": {key: verse[key] for key in ("translation", "book", "chapter", "verse")},
  }


def preview_picture(text: str) -> dict:
  """The leader's words over a random verse a day picture, saved so the same card can be sent."""
  text = _text(text, "words for the picture", PICTURE_TEXT_LIMIT)
  card = message_cards.make_card(text, "", plain_if_none=True)
  if card is None:
    raise GroupProblem("The picture could not be made; try again.")
  return {"card": card.path.name, "image": message_cards.data_address(card), "words": text}


# --- sending -----------------------------------------------------------------------------------------------


def compose_email(
  settings: dict, group: dict, token: str | None, subject: str, text: str, verse: dict | None, card, reached: int = 0
) -> EmailMessage:
  """One copy of a group email. Its To is the leader, never the member: send it with send_email(..., [member's
  address]). token is the member's stop link; None makes the leader's own copy (no stop link; it says how many
  it went to)."""
  title = get_public_settings()["title"]
  site = site_link("").rstrip("?")
  email = EmailMessage()
  email["Subject"] = subject
  email["From"] = settings["from_address"]
  email["To"] = group["owner_email"] or settings["from_address"]
  if group["owner_email"]:
    email["Reply-To"] = group["owner_email"]
  if token:
    one_click = site.rstrip("/") + "/api/subscriptions/unsubscribe?token=" + token
    email["List-Unsubscribe"] = f"<{one_click}>"
    email["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
  if verse:
    lines = [verse["text"], verse["caption"], "", f"Read it in context: {verse_a_day.verse_link(verse['verse'])}"]
  else:
    lines = [text]
  sender = group["owner_name"] or "the group's leader"
  lines += ["", "--", f"Sent by {sender} to the group “{group['name']}” through {title}: {site}"]
  if token:
    lines.append(f"To stop messages from this group, open: {site_link('unsubscribe=' + token)}")
  else:
    lines.append(f"This is your copy as the group's leader: it went to {reached} member{'s' if reached != 1 else ''}, each as a hidden recipient.")
  email.set_content("\n".join(lines) + "\n")
  if verse:
    message_cards.attach_to_email(email, card, f"{verse['text']} {verse['caption']}", link=verse_a_day.verse_link(verse["verse"]), linked_lines=2)
  elif card is not None:
    message_cards.attach_to_email(email, card, text)
  return email


def send(group_id: int, kind: str, details: dict, sent_by: str, pause: float = PAUSE_BETWEEN_MEMBERS) -> dict:
  """Sends one message to every member who has not stopped them. details: subject and text (message, picture),
  card (verse, picture: the name from the preview) and verse (verse: translation, book, chapter, verse).
  Returns how many were emailed, texted, skipped (not confirmed yet, or stopped) and failed."""
  if kind not in KINDS:
    raise GroupProblem("Unknown kind of message.")
  group = get_group(group_id)
  card = None
  verse = None
  if kind in ("verse", "picture"):
    card = message_cards.card_from_name(details.get("card", ""))
    if card is None:
      raise GroupProblem("The picture is no longer there (pictures are kept a week); make the preview again.")
  if kind == "verse":
    chosen = details.get("verse") or {}
    try:
      verse = day_cards.find_verse(str(chosen["translation"]), int(chosen["book"]), int(chosen["chapter"]), int(chosen["verse"]))
    except (KeyError, TypeError, ValueError):
      verse = None
    if verse is None:
      raise GroupProblem("The verse was not found; make the preview again.")
    subject = f"A verse for {group['name']}: {verse['reference']}"
    text = verse["text"]
    words, link = f"{verse['reference']}: {verse['text']}", verse_a_day.verse_link(verse["verse"])
  else:
    subject = _one_line(details.get("subject", ""), "subject", SUBJECT_LIMIT)
    text = _text(details.get("text", ""), "message" if kind == "message" else "words for the picture", MESSAGE_LIMIT if kind == "message" else PICTURE_TEXT_LIMIT)
    words, link = f"{group['name']}: {subject}. {text}", ""

  with connect() as connection:
    members = connection.execute(
      """
      SELECT m.user_id, COALESCE(u.email, m.email), m.stop_token, m.stopped_at IS NOT NULL,
             m.user_id IS NULL OR u.email_verified_at IS NOT NULL
      FROM group_members m LEFT JOIN users u ON u.id = m.user_id WHERE m.group_id = %s ORDER BY m.id
      """,
      (group_id,),
    ).fetchall()
  counts = {"emailed": 0, "texted": 0, "skipped": 0, "failed": 0}
  # Members reached by email, text or both (for the leader's copy).
  reached = 0
  settings = None
  for user_id, address, token, stopped, confirmed in members:
    if stopped or not confirmed:
      counts["skipped"] += 1
      continue

    def send_the_email(address=address, token=token):
      nonlocal settings
      if settings is None:
        settings = load_mail_settings()
      # The member is the hidden recipient; the To shows the leader.
      send_email(settings, compose_email(settings, group, token, subject, text, verse, card), [address])

    try:
      if user_id is None:
        # A contact: email only (nobody has their agreement to texts).
        send_the_email()
        counts["emailed"] += 1
        reached += 1
      else:
        sent = sms.deliver(user_id, send_the_email, words, link, card)
        counts["emailed"] += int(sent["email"])
        counts["texted"] += int(sent["text"])
        reached += int(sent["email"] or sent["text"])
    except Exception as problem:  # one member's failure never stops the others
      logger.error("Group %s message not sent to a member: %s: %s", group_id, type(problem).__name__, problem if isinstance(problem, MailUnavailable) else "")
      counts["failed"] += 1
    if pause:
      time.sleep(pause)

  # The leader's own copy, once per send (never one per member).
  if group["owner_email"] and reached:
    try:
      if settings is None:
        settings = load_mail_settings()
      send_email(settings, compose_email(settings, group, None, subject, text, verse, card, reached), [group["owner_email"]])
    except Exception as problem:
      logger.error("Group %s leader's copy not sent: %s", group_id, type(problem).__name__)

  with connect() as connection:
    connection.execute(
      """
      INSERT INTO group_messages (group_id, kind, subject, text, sent_by, emailed, texted, skipped, failed)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
      """,
      (group_id, kind, subject, text, sent_by, counts["emailed"], counts["texted"], counts["skipped"], counts["failed"]),
    )
  return counts


def list_sent(group_id: int, limit: int = 20) -> list[dict]:
  """The group's latest messages, newest first."""
  with connect() as connection:
    rows = connection.execute(
      """
      SELECT kind, subject, text, sent_by, emailed, texted, skipped, failed, sent_at
      FROM group_messages WHERE group_id = %s ORDER BY sent_at DESC, id DESC LIMIT %s
      """,
      (group_id, limit),
    ).fetchall()
  return [
    {"kind": row[0], "subject": row[1], "text": row[2], "sent_by": row[3], "emailed": row[4], "texted": row[5],
     "skipped": row[6], "failed": row[7], "sent_at": row[8].isoformat()}
    for row in rows
  ]
