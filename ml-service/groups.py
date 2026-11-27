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
was sent is kept in group_messages with counts; since 2026-11-18 (the owner's request: "an exact copy of the
email sent (to, bcc, subject, contents)") group_message_copies also keeps the email as it went out, with the
addresses it was emailed to (keep_copy, get_copy).
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
from html import escape

from contact import CONTROL_CHARACTERS, ContactProblem, FormattedCleaner, MailUnavailable, check_rich_text, load_mail_settings, send_email
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger("groups")

NAME_LIMIT = 200
DESCRIPTION_LIMIT = 2_000
# The Description (headline): one line, the title of the group's sign-up sheet.
HEADLINE_LIMIT = 120
SUBJECT_LIMIT = 200
MESSAGE_LIMIT = 5_000
# Words on a picture message: more would be too small to read.
PICTURE_TEXT_LIMIT = 400
MAX_MEMBERS = 500
PAUSE_BETWEEN_MEMBERS = 0.5
KINDS = ("message", "verse", "picture")
# The member code in the stop links of the copy kept of a sent email (group_message_copies): each member's links
# carry their own, so the copy shows this instead. It matches no member, so the links stop nothing.
STOP_CODE_PLACEHOLDER = "MEMBER-STOP-CODE"


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
    # Its Description (migration 076): one line, the title of its sign-up sheet ('' for none).
    "headline": row[9],
  }


GROUP_COLUMNS = """
  g.id, g.name, g.description, g.owner_uid, g.owner_name, g.owner_email, g.created_at,
  (SELECT count(*) FROM group_members m WHERE m.group_id = g.id),
  (SELECT max(sent_at) FROM group_messages s WHERE s.group_id = g.id),
  g.headline
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
  if details.get("description_html") is not None:
    # The leader's notes written in the editor (2026-11-17): cleaned like a message (only the allowed tags), or ""
    # when there is nothing in them. The group page shows them formatted.
    raw = str(details["description_html"])
    try:
      description = check_rich_text(raw, DESCRIPTION_LIMIT * 10, DESCRIPTION_LIMIT, "notes", FormattedCleaner)["html"]
    except ContactProblem as problem:
      if "write something" not in str(problem):
        raise GroupProblem(str(problem)) from problem
      description = ""
  else:
    description = (details.get("description") or "").strip()[:DESCRIPTION_LIMIT]
  # The Description (one line; the sign-up sheet's title). Left out of a change, it stays.
  headline = None
  if details.get("headline") is not None:
    headline = " ".join(str(details["headline"]).split())
    if len(headline) > HEADLINE_LIMIT:
      raise GroupProblem(f"The description can be up to {HEADLINE_LIMIT} characters.")
  with connect() as connection:
    if group_id is None:
      group_id = connection.execute(
        "INSERT INTO member_groups (name, description, headline, owner_uid, owner_name, owner_email) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (name, description, headline or "", owner_uid, owner_name, owner_email),
      ).fetchone()[0]
    else:
      changed = connection.execute(
        """
        UPDATE member_groups SET name = %s, description = %s, headline = COALESCE(%s, headline),
          owner_name = CASE WHEN owner_uid = %s THEN %s ELSE owner_name END,
          owner_email = CASE WHEN owner_uid = %s THEN %s ELSE owner_email END
        WHERE id = %s RETURNING id
        """,
        (name, description, headline, owner_uid, owner_name, owner_uid, owner_email, group_id),
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
  (u.email_verified_at IS NOT NULL OR u.phone_verified_at IS NOT NULL), m.schedules_stopped_at IS NOT NULL,
  (SELECT count(*) FROM group_schedule_stops s WHERE s.member_id = m.id), u.disabled_at IS NOT NULL
"""


def _how(connection, user_id: int | None, verified: bool, stopped: bool, closed: bool = False) -> str:
  """How the group's messages reach a member, in words for the leader."""
  if closed:
    return "Nothing: they closed their account"
  if stopped:
    return "Stopped (they followed the stop link in an email)"
  if user_id is None:
    return "Email"
  if not verified:
    return "Nothing until they confirm their email address or phone number"
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
        "id": row[0], "is_account": row[1] is not None, "user_id": row[1], "stopped": row[2] is not None,
        "confirmed": row[1] is None or (bool(row[6]) and not row[9]), "closed": bool(row[9]),
        "name": row[3], "email": row[4] or "", "phone": row[5],
        "receives": _how(connection, row[1], row[6], row[2] is not None, bool(row[9])),
        # Scheduled emails they stopped: all of them, or how many (stop_schedule_with_token).
        "schedules_stopped": bool(row[7]), "stopped_schedules": row[8],
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
      SELECT u.id, COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), ''), COALESCE(u.email, u.phone, ''),
             (u.email_verified_at IS NOT NULL OR u.phone_verified_at IS NOT NULL)
      FROM users u
      WHERE u.disabled_at IS NULL AND NOT EXISTS (SELECT 1 FROM group_members m WHERE m.group_id = %s AND m.user_id = u.id)
      ORDER BY lower(COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), u.email, u.phone)), u.id
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


def restart_schedules(group_id: int, member_id: int) -> dict:
  """Undoes a member's stopped scheduled emails (the group page's "Start scheduled emails again"; added 2026-11-17 at
  the owner's request): both the ones they stopped one by one and "all scheduled emails from this group". It does
  not undo the group's own stop link (stopped_at: everything from the group). Returns the member."""
  with connect() as connection:
    found = connection.execute("SELECT 1 FROM group_members WHERE id = %s AND group_id = %s", (member_id, group_id)).fetchone()
    if found is None:
      raise GroupProblem("That member is not in the group (they may have been removed).")
    connection.execute("DELETE FROM group_schedule_stops WHERE member_id = %s", (member_id,))
    connection.execute("UPDATE group_members SET schedules_stopped_at = NULL WHERE id = %s", (member_id,))
  return next(member for member in list_members(group_id) if member["id"] == member_id)


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


def schedule_stop_token(token: str, schedule_id) -> str:
  """The token of a scheduled email's stop links: the member's stop_token (token_urlsafe, never a dot) with
  ".s<schedule id>" (this scheduled email) or ".sall" (all the group's scheduled emails). The site's stop page and
  the one-click endpoint pass it to subscriptions.unsubscribe_with_token like any other."""
  return f"{token}.s{schedule_id}"


def stop_schedule_with_token(connection, token: str) -> tuple[str, str] | None:
  """A scheduled email's stop link (schedule_stop_token): records that the member stopped that scheduled email
  (group_schedule_stops) or all the group's scheduled emails (group_members.schedules_stopped_at). The member stays
  in the group and still gets what the leader sends by hand. Returns what was stopped, in words, and the sentence
  the stop page shows (2026-11-17: "clearer wording"), or None when the token is not one of these."""
  match = re.fullmatch(r"([A-Za-z0-9_-]{8,64})\.s(all|\d{1,9})", token or "")
  if match is None:
    return None
  member = connection.execute(
    "SELECT m.id, m.group_id, g.name FROM group_members m JOIN member_groups g ON g.id = m.group_id WHERE m.stop_token = %s",
    (match[1],),
  ).fetchone()
  if member is None:
    return None
  member_id, group_id, group_name = member
  if match[2] == "all":
    connection.execute("UPDATE group_members SET schedules_stopped_at = COALESCE(schedules_stopped_at, now()) WHERE id = %s", (member_id,))
    return (
      f"the scheduled emails from the group “{group_name}” (you stay in the group)",
      f"You will not get any scheduled emails from the group “{group_name}” any more. You are still in the group, and "
      "still get the messages your leader sends.",
    )
  schedule = connection.execute(
    "SELECT kind, subject FROM group_schedules WHERE id = %s AND group_id = %s", (int(match[2]), group_id)
  ).fetchone()
  if schedule is None:
    return None
  connection.execute(
    "INSERT INTO group_schedule_stops (schedule_id, member_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (int(match[2]), member_id)
  )
  what = "verse card" if schedule[0] == "verse" else f"“{schedule[1]}”"
  sentence_what = "the scheduled verse card" if schedule[0] == "verse" else f"the scheduled email “{schedule[1]}”"
  return (
    f"the scheduled {what} from the group “{group_name}” (you stay in the group)",
    f"You will not get {sentence_what} from the group “{group_name}” any more. You are still in the group, and still "
    "get the messages your leader sends and its other scheduled emails.",
  )


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
  settings: dict, group: dict, token: str | None, subject: str, text: str, verse: dict | None, card, reached: int = 0,
  personal: bool = False, html: str | None = None, schedule: dict | None = None, to_address: str | None = None,
  signature: dict | None = None, show_sent_by: bool = True, card_attachment: bool = False,
) -> EmailMessage:
  """One copy of a group email. show_sent_by: False leaves out the "Sent by … through …" line of the foot
  ("Add the “Sent by …” line", 2026-11-23); the member's stop links stay. Its To is the leader, never the member: send it with send_email(..., [member's
  address]). token is the member's stop link; None makes the leader's own copy (no stop link; it says how many
  it went to). personal: a message to that one member (email_member, sent at once or at its "Send at" time): only
  the leader's words, with **no foot** (no "Sent by ..." line, no stop link and no one-click header; the owner's
  request, 2026-11-18: "This is not a group email so we don't need it"); token is then not used, and its To is
  the member's own address (to_address; the same day: "make the to address the destination email and remove it from
  the bcc"), so it is sent to them openly, not as a hidden recipient. html: the message
  as cleaned HTML (from the editor; text is then its plain-text copy), sent as an HTML part with the same foot.
  schedule ({id, label}): a scheduled email (group_schedules.send_due). Its foot has two more stop links, for this
  scheduled email only and for all the group's scheduled emails (schedule_stop_link; stop_schedule_with_token),
  and its one-click header stops this scheduled email only. Neither takes the member out of the group.
  signature ({html, text}): the signature chosen for a scheduled email (2026-11-19, the owner's request: "Each
  schedule can have a different signature"), after the words and before the foot. card_attachment: the card is the
  leader's saved verse card attached to a message (2026-11-26): shown in the email and attached as a JPEG."""
  title = get_public_settings()["title"]
  site = site_link("").rstrip("?")
  email = EmailMessage()
  email["Subject"] = subject
  email["From"] = settings["from_address"]
  email["To"] = to_address if personal and to_address else (group["owner_email"] or settings["from_address"])
  if group["owner_email"]:
    email["Reply-To"] = group["owner_email"]
  if personal:
    # A message to one member is not a group email: the leader's words only, and the signature chosen on the box
    # (2026-11-19) after them.
    if signature and signature.get("text"):
      text = f"{text}\n\n{signature['text']}"
      if html is not None:
        html += signature["html"]
    email.set_content(text + "\n")
    if html is not None:
      email.add_alternative(f"<html><body>{html}</body></html>", subtype="html")
    if card is not None:
      # The leader's saved verse card (2026-11-26): in the email and attached.
      message_cards.attach_card_file(email, card, text)
    return email
  if token:
    one_click = site.rstrip("/") + "/api/subscriptions/unsubscribe?token=" + (schedule_stop_token(token, schedule["id"]) if schedule else token)
    email["List-Unsubscribe"] = f"<{one_click}>"
    email["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
  if verse:
    lines = [verse["text"], verse["caption"], "", f"Read it in context: {verse_a_day.verse_link(verse['verse'])}"]
  else:
    lines = [text]
  if signature and signature.get("text"):
    lines += ["", signature["text"]]
    if html is not None:
      html += signature["html"]
  sender = group["owner_name"] or "the group's leader"
  lines += ["", "--"]
  if show_sent_by:
    lines.append(f"Sent by {sender} to the group “{group['name']}” through {title}: {site}")
  links = []
  if token:
    if schedule:
      links.append(site_link("unsubscribe=" + schedule_stop_token(token, schedule["id"])))
      lines.append(f"To stop this scheduled email ({schedule['label']}), open: {links[-1]}")
      links.append(site_link("unsubscribe=" + schedule_stop_token(token, "all")))
      lines.append(f"To stop all scheduled emails from this group, open: {links[-1]}")
      lines.append("You stay in the group, and still get the messages your leader sends.")
    links.append(site_link("unsubscribe=" + token))
    lines.append(f"To stop all messages from this group, open: {links[-1]}" if schedule else f"To stop messages from this group, open: {links[-1]}")
  else:
    lines.append(f"This is your copy as the group's leader: it went to {reached} member{'s' if reached != 1 else ''}, each as a hidden recipient.")
  email.set_content("\n".join(lines) + "\n")
  if html is not None:
    foot = "".join(f"<p>{escape(line)}</p>" for line in lines[len(lines) - lines[::-1].index("--"):])
    # Every stop link made a link in one pass, the longest first: the group's own stop address is the start of the
    # scheduled email's ones (...?unsubscribe=TOKEN and ...?unsubscribe=TOKEN.s12), so replacing them one after
    # the other put a link inside a link (found 2026-11-19).
    if links:
      addresses = re.compile("|".join(re.escape(escape(stop)) for stop in sorted(set(links), key=len, reverse=True)))
      foot = addresses.sub(lambda found: f'<a href="{found.group(0)}">{found.group(0)}</a>', foot)
    email.add_alternative(f"<html><body>{html}<hr>{foot}</body></html>", subtype="html")
  if verse:
    message_cards.attach_to_email(email, card, f"{verse['text']} {verse['caption']}", link=verse_a_day.verse_link(verse["verse"]), linked_lines=2)
  elif card is not None and card_attachment:
    message_cards.attach_card_file(email, card, text)
  elif card is not None:
    message_cards.attach_to_email(email, card, text)
  return email


def message_html(html: str) -> tuple[str, str]:
  """A message written in the editor (Drupal's CKEditor, text format group_email; the owner's request, 2026-11-17):
  cleaned like the contact form's messages (contact.check_rich_text: only its allowed tags, links only http(s) or
  mailto, no attributes). Returns (html, text): the HTML for the email and its plain-text copy for texts."""
  try:
    cleaned = check_rich_text(html, MESSAGE_LIMIT * 10, MESSAGE_LIMIT, "message", FormattedCleaner)
  except ContactProblem as problem:
    raise GroupProblem(str(problem)) from problem
  return cleaned["html"], cleaned["text"]


def _prepare(group: dict, kind: str, details: dict) -> tuple:
  """What a send of this kind says, from its details (see send): subject, text, verse, card, the words and link of
  its text message, and html (a message written in the editor: details["html"]; else None)."""
  if kind not in KINDS:
    raise GroupProblem("Unknown kind of message.")
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
  html = None
  if kind != "verse":
    subject = _one_line(details.get("subject", ""), "subject", SUBJECT_LIMIT)
    if kind == "message" and details.get("html") is not None:
      html, text = message_html(str(details["html"]))
    else:
      text = _text(details.get("text", ""), "message" if kind == "message" else "words for the picture", MESSAGE_LIMIT if kind == "message" else PICTURE_TEXT_LIMIT)
    words, link = f"{group['name']}: {subject}. {text}", ""
    if kind == "message" and details.get("saved_card"):
      card = _saved_card(details)

  return subject, text, verse, card, words, link, html


def card_owner(details: dict) -> tuple[int, int] | None:
  """The saved verse card chosen (details["saved_card"]) and the site account it must belong to: the sender's,
  found from details["admin"] (their Drupal uid and email; saved_cards.account_for_admin), or, for a scheduled
  message, details["card_user_id"] (kept when it was set up; never taken from Drupal's input, which the tool strips).
  (user id, card id), None when no card was chosen; GroupProblem when it is not the sender's."""
  import saved_cards

  if not details.get("saved_card"):
    return None
  try:
    card_id = int(details["saved_card"])
    if details.get("card_user_id"):
      user_id = int(details["card_user_id"])
    else:
      admin = details.get("admin") or {}
      account = saved_cards.account_for_admin(int(admin.get("uid") or 0), str(admin.get("email") or ""))
      if account is None:
        raise GroupProblem("Your Drupal account is not linked to a site account, so it has no saved cards.")
      user_id = account["id"]
    saved_cards.get_card(user_id, card_id)
  except (TypeError, ValueError) as error:
    raise GroupProblem("That card could not be found.") from error
  except saved_cards.SavedCardProblem as problem:
    raise GroupProblem(f"The card could not be attached: {problem}") from problem
  return user_id, card_id


def _saved_card(details: dict):
  """The sender's own saved verse card for a message (card_owner), copied so a text can fetch it; None without one."""
  import saved_cards

  owner = card_owner(details)
  if owner is None:
    return None
  try:
    return saved_cards.card_for_sending(*owner)
  except saved_cards.SavedCardProblem as problem:
    raise GroupProblem(f"The card could not be attached: {problem}") from problem


def send(
  group_id: int, kind: str, details: dict, sent_by: str, pause: float = PAUSE_BETWEEN_MEMBERS, schedule: dict | None = None
) -> dict:
  """Sends one message to every member who has not stopped them. details: subject and text (message, picture),
  card (verse, picture: the name from the preview) and verse (verse: translation, book, chapter, verse).
  schedule ({id, label}): sent by a scheduled email, which also skips the members who stopped it or all the
  group's scheduled emails, and gives the others its own stop links (compose_email).
  Returns how many were emailed, texted, skipped (not confirmed yet, or stopped) and failed."""
  # "Add the “Sent by …” line" (2026-11-23): on unless the leader unticked it.
  show_sent_by = details.get("show_sent_by", True) is not False
  group = get_group(group_id)
  # A scheduled email's signature ({html, text}; group_schedules), in every copy of it; for one sent now, the one
  # chosen on Send a message (details["signature_id"], one of the leader's; 2026-11-26).
  signature = (schedule or {}).get("signature")
  if schedule is None and details.get("signature_id") not in (None, ""):
    signature = signature_words(leader_signature(group, details.get("signature_id")))
  subject, text, verse, card, words, link, html = _prepare(group, kind, details)
  card_attachment = kind == "message"

  with connect() as connection:
    members = connection.execute(
      """
      SELECT m.user_id, COALESCE(u.email, m.email), m.stop_token,
             m.stopped_at IS NOT NULL OR (%(schedule)s::int IS NOT NULL AND (m.schedules_stopped_at IS NOT NULL
               OR EXISTS (SELECT 1 FROM group_schedule_stops s WHERE s.member_id = m.id AND s.schedule_id = %(schedule)s))),
             m.user_id IS NULL OR ((u.email_verified_at IS NOT NULL OR u.phone_verified_at IS NOT NULL) AND u.disabled_at IS NULL)
      FROM group_members m LEFT JOIN users u ON u.id = m.user_id WHERE m.group_id = %(group)s ORDER BY m.id
      """,
      {"group": group_id, "schedule": schedule["id"] if schedule else None},
    ).fetchall()
  counts = {"emailed": 0, "texted": 0, "skipped": 0, "failed": 0}
  # Members reached by email, text or both (for the leader's copy).
  reached = 0
  # The addresses it was emailed to (the hidden recipients), for the copy kept (keep_copy).
  bcc = []
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
      send_email(settings, compose_email(settings, group, token, subject, text, verse, card, schedule=schedule, html=html, signature=signature, show_sent_by=show_sent_by, card_attachment=card_attachment), [address])
      bcc.append(address)

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
  leader_copy = False
  if group["owner_email"] and reached:
    try:
      if settings is None:
        settings = load_mail_settings()
      send_email(settings, compose_email(settings, group, None, subject, text, verse, card, reached, html=html, signature=signature, show_sent_by=show_sent_by, card_attachment=card_attachment), [group["owner_email"]])
      leader_copy = True
    except Exception as problem:
      logger.error("Group %s leader's copy not sent: %s", group_id, type(problem).__name__)

  with connect() as connection:
    message_id = connection.execute(
      """
      INSERT INTO group_messages (group_id, kind, subject, text, sent_by, emailed, texted, skipped, failed)
      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
      """,
      (group_id, kind, subject, text, sent_by, counts["emailed"], counts["texted"], counts["skipped"], counts["failed"]),
    ).fetchone()[0]
    if bcc or leader_copy:
      # A member's copy (their stop code replaced), or the leader's when no member was emailed (texts only).
      copy = compose_email(
        settings, group, STOP_CODE_PLACEHOLDER if bcc else None, subject, text, verse, card, reached,
        schedule=schedule if bcc else None, html=html, signature=signature, show_sent_by=show_sent_by,
        card_attachment=card_attachment,
      )
      keep_copy(connection, message_id, copy, bcc, leader_copy)
  return counts


def send_test(group_id: int, kind: str, details: dict, schedule: dict | None = None) -> dict:
  """A test of a message (a scheduled email's "Send a test", group_schedules.send_test; added 2026-11-17 at the
  owner's request), sent **only to the group's leader** (their Drupal address, the group's Reply-To). It is
  **exactly** what a member gets (the owner's request: "I want to see EXACTLY what the users will see"): the same
  subject, words and foot, with schedule ({id, label}) its scheduled-email stop links, and the one-click header.
  The links carry a made-up member code that matches nobody, so they look like a member's
  but stop nothing. Email only (no texts), not recorded in the Sent table. Returns the address it went to."""
  group = get_group(group_id)
  if not group["owner_email"]:
    raise GroupProblem("The group's leader has no email address: set one on their Drupal account first.")
  subject, text, verse, card, _words, _link, html = _prepare(group, kind, details)
  try:
    settings = load_mail_settings()
    # A code shaped like a member's stop_token that belongs to no one (the stop page says "not valid").
    email = compose_email(
      settings, group, secrets.token_urlsafe(24), subject, text, verse, card, schedule=schedule, html=html,
      signature=(schedule or {}).get("signature"), show_sent_by=details.get("show_sent_by", True) is not False,
      card_attachment=kind == "message",
    )
    send_email(settings, email, [group["owner_email"]])
  except MailUnavailable as problem:
    raise GroupProblem(f"The test could not be sent: {problem}") from problem
  except Exception as problem:
    logger.error("Group %s test not sent: %s", group_id, type(problem).__name__)
    raise GroupProblem("The test could not be sent; try again later.") from problem
  return {"to": group["owner_email"]}


# --- signatures (admin_signatures; signatures.py) ---------------------------------------------------------


def leader_signature(group: dict, value) -> int | None:
  """The signature chosen for a scheduled email or Email a member (details["signature_id"]; 2026-11-19), checked to
  be one of the group leader's; None (or "") for none."""
  if value is None or value == "":
    return None
  if isinstance(value, str) and value.strip().isdigit():
    value = int(value.strip())
  if not isinstance(value, int) or isinstance(value, bool):
    raise GroupProblem("Choose one of the leader's signatures, or no signature.")
  with connect() as connection:
    found = connection.execute("SELECT 1 FROM admin_signatures WHERE id = %s AND owner_uid = %s", (value, group["owner_uid"])).fetchone()
  if found is None:
    raise GroupProblem("That signature is not one of the group leader's (it may have been deleted).")
  return value


def signature_words(signature_id: int | None) -> dict | None:
  """A signature as an email needs it ({html, text}), read when the email goes; None for none (or one deleted)."""
  if not signature_id:
    return None
  with connect() as connection:
    row = connection.execute("SELECT html, text FROM admin_signatures WHERE id = %s", (signature_id,)).fetchone()
  return {"html": row[0], "text": row[1]} if row else None


def email_member(
  group_id: int, member_id: int, text: str, sent_by: str, html: str | None = None, subject: str | None = None,
  signature: dict | None = None, card=None,
) -> dict:
  """A message from the leader to **one member** (the Email link in the group's member list; added 2026-11-17 at
  the owner's request). By email only, to that member alone: From the site, **To the member's own address** (no
  hidden recipients; 2026-11-18), Reply-To the leader, and only the leader's words, with no group foot or stop link
  (2026-11-18, the owner's request: "This is not a group email"). Refused
  for a member who stopped the group's messages or whose site address is not confirmed yet (a group send skips
  them too). No leader's copy. Recorded in the group's Sent table as a message "to one member" (never who).
  html (from the Drupal box's editor, CKEditor 5) is cleaned like the contact form's messages
  (contact.check_rich_text: only its allowed tags, links only http(s) or mailto, no attributes) and sent as HTML
  with a plain-text copy; without it, text is sent as plain text. card: the leader's saved verse card (a
  message_cards.MessageCard; 2026-11-26), shown in the email and attached. Returns the member (id, name)."""
  text, html = member_message(text, html)
  group = get_group(group_id)
  address, token = member_recipient(group_id, member_id)
  subject = member_subject(group, subject)
  try:
    settings = load_mail_settings()
    # To the member openly (their address is the To, not a hidden recipient); replies go to the leader.
    send_email(settings, compose_email(settings, group, token, subject, text, None, card, personal=True, html=html, to_address=address, signature=signature))
  except MailUnavailable as problem:
    raise GroupProblem(f"The email could not be sent: {problem}") from problem
  except Exception as problem:
    logger.error("Group %s message to member %s not sent: %s", group_id, member_id, type(problem).__name__)
    raise GroupProblem("The email could not be sent; try again later.") from problem
  with connect() as connection:
    message_id = connection.execute(
      "INSERT INTO group_messages (group_id, kind, subject, text, sent_by, emailed) VALUES (%s, 'message', %s, %s, %s, 1) RETURNING id",
      (group_id, subject + " (to one member)", text, sent_by),
    ).fetchone()[0]
    copy = compose_email(settings, group, STOP_CODE_PLACEHOLDER, subject, text, None, card, personal=True, html=html, to_address=address, signature=signature)
    keep_copy(connection, message_id, copy, [], False)
  member = next(member for member in group["members"] if member["id"] == member_id)
  return {"id": member["id"], "name": member["name"]}


def member_message(text: str, html: str | None) -> tuple[str, str | None]:
  """A message to one member, checked: (text, html). html (the editor's) is cleaned like the contact form's and
  text becomes its plain-text copy; without it, text is checked as plain text."""
  if html is not None:
    try:
      cleaned = check_rich_text(html, MESSAGE_LIMIT * 10, MESSAGE_LIMIT, "message", FormattedCleaner)
    except ContactProblem as problem:
      raise GroupProblem(str(problem)) from problem
    return cleaned["text"], cleaned["html"]
  return _text(text, "message", MESSAGE_LIMIT), None


def member_subject(group: dict, typed: str | None = None) -> str:
  """The subject of a message to one member: the one the leader typed in the box's Subject (added 2026-11-18 at the
  owner's request), checked as one line of plain text, else "A message from <the leader> (<the group>)" (which the
  box starts with)."""
  chosen = _one_line(typed or "", "subject", SUBJECT_LIMIT, required=False)
  if chosen:
    return chosen
  sender = group["owner_name"] or "your group's leader"
  return f"A message from {sender} ({group['name']})"


def member_recipient(group_id: int, member_id: int) -> tuple[str, str]:
  """The address and stop token of a member who can be emailed now; raises GroupProblem saying why not (closed
  account, stopped the group's messages, no email address, address not confirmed)."""
  with connect() as connection:
    row = connection.execute(
      """
      SELECT COALESCE(u.email, m.email), m.stop_token, m.stopped_at IS NOT NULL,
             m.user_id IS NULL OR (u.email_verified_at IS NOT NULL OR u.phone_verified_at IS NOT NULL), u.disabled_at IS NOT NULL
      FROM group_members m LEFT JOIN users u ON u.id = m.user_id WHERE m.id = %s AND m.group_id = %s
      """,
      (member_id, group_id),
    ).fetchone()
  if row is None:
    raise GroupProblem("That member is not in the group (they may have been removed).")
  address, token, stopped, confirmed, closed = row
  if closed:
    raise GroupProblem("This member closed their account, so nothing can be sent to them.")
  if stopped:
    raise GroupProblem("This member stopped the group's messages, so nothing can be sent to them.")
  if address is None:
    raise GroupProblem("This member's account has no email address (they log in with their phone), so it cannot be emailed.")
  if not confirmed:
    raise GroupProblem("This member has not confirmed their email address yet, so nothing can be sent to them.")
  return address, token


def send_prayer_request(
  group_id: int, share_with: str, author_id: int, author_name: str, author_email: str, title: str, text: str,
  pause: float = PAUSE_BETWEEN_MEMBERS,
) -> dict:
  """A Prayer Wall request its author chose to email to their group ("Email <group>": every member but the author,
  each the way they chose, as a group message) or to its leader ("Email <group> leader": the leader's address
  only). Sent at once; the request is private on the site. Reply-To is the author, so answers go to them; the To
  shows the leader and members are hidden recipients, as for every group email. Recorded in the group's Sent
  table (the subject only: the request is private). Returns the counts."""
  group = get_group(group_id)
  title_line = get_public_settings()["title"]
  site = site_link("").rstrip("?")
  subject = f"Prayer request from {author_name}: {title}"[:SUBJECT_LIMIT]
  to_whom = f"the group “{group['name']}”" if share_with == "group" else f"you, the leader of “{group['name']}”"

  def compose(settings: dict, token: str | None) -> EmailMessage:
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = settings["from_address"]
    email["To"] = group["owner_email"] or settings["from_address"]
    if author_email:
      email["Reply-To"] = author_email
    lines = [
      text.strip(),
      "",
      "--",
      f"{author_name} sent this prayer request from the Prayer Wall of {title_line} to {to_whom}. It is private on "
      "the site. Reply to this email to answer them.",
      site,
    ]
    if token:
      one_click = site.rstrip("/") + "/api/subscriptions/unsubscribe?token=" + token
      email["List-Unsubscribe"] = f"<{one_click}>"
      email["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
      lines.append(f"To stop messages from this group, open: {site_link('unsubscribe=' + token)}")
    email.set_content("\n".join(lines) + "\n")
    return email

  counts = {"emailed": 0, "texted": 0, "skipped": 0, "failed": 0}
  # The addresses it was emailed to as hidden recipients, and whether the leader's address got it (keep_copy).
  bcc = []
  leader_copy = False
  settings = None

  def mail_settings() -> dict:
    nonlocal settings
    if settings is None:
      settings = load_mail_settings()
    return settings

  if share_with == "leader":
    if not group["owner_email"]:
      counts["skipped"] = 1
    else:
      try:
        send_email(mail_settings(), compose(mail_settings(), None), [group["owner_email"]])
        counts["emailed"] = 1
        leader_copy = True
      except Exception as problem:
        logger.error("Prayer request to group %s's leader not sent: %s", group_id, type(problem).__name__)
        counts["failed"] = 1
  else:
    with connect() as connection:
      members = connection.execute(
        """
        SELECT m.user_id, COALESCE(u.email, m.email), m.stop_token, m.stopped_at IS NOT NULL,
               m.user_id IS NULL OR ((u.email_verified_at IS NOT NULL OR u.phone_verified_at IS NOT NULL) AND u.disabled_at IS NULL)
        FROM group_members m LEFT JOIN users u ON u.id = m.user_id
        WHERE m.group_id = %s AND m.user_id IS DISTINCT FROM %s ORDER BY m.id
        """,
        (group_id, author_id),
      ).fetchall()
    for user_id, address, token, stopped, confirmed in members:
      if stopped or not confirmed:
        counts["skipped"] += 1
        continue

      def send_the_email(address=address, token=token):
        send_email(mail_settings(), compose(mail_settings(), token), [address])
        bcc.append(address)

      try:
        if user_id is None:
          send_the_email()
          counts["emailed"] += 1
        else:
          sent = sms.deliver(user_id, send_the_email, f"Prayer request from {author_name}: {title}. {text}")
          counts["emailed"] += int(sent["email"])
          counts["texted"] += int(sent["text"])
      except Exception as problem:
        logger.error("Prayer request to group %s not sent to a member: %s", group_id, type(problem).__name__)
        counts["failed"] += 1
      if pause:
        time.sleep(pause)
    # The leader's copy, as for every message to the group.
    if group["owner_email"] and counts["emailed"] + counts["texted"]:
      try:
        send_email(mail_settings(), compose(mail_settings(), None), [group["owner_email"]])
        leader_copy = True
      except Exception as problem:
        logger.error("Prayer request: group %s leader's copy not sent: %s", group_id, type(problem).__name__)

  with connect() as connection:
    message_id = connection.execute(
      """
      INSERT INTO group_messages (group_id, kind, subject, text, sent_by, emailed, texted, skipped, failed)
      VALUES (%s, 'message', %s, '', %s, %s, %s, %s, %s) RETURNING id
      """,
      (group_id, subject + (" (to the leader)" if share_with == "leader" else ""), f"Prayer Wall ({author_name})",
       counts["emailed"], counts["texted"], counts["skipped"], counts["failed"]),
    ).fetchone()[0]
    if bcc or leader_copy:
      # To the leader only, the leader's email is the one kept (bcc empty: it went to its To alone, and
      # leader_copy is false, as there was no separate copy); else a member's, their stop code replaced.
      copy = compose(mail_settings(), STOP_CODE_PLACEHOLDER if bcc else None)
      keep_copy(connection, message_id, copy, bcc, leader_copy and share_with == "group")
  return counts


def list_sent(group_id: int, limit: int = 20) -> list[dict]:
  """The group's latest messages, newest first."""
  with connect() as connection:
    rows = connection.execute(
      """
      SELECT kind, subject, text, sent_by, emailed, texted, skipped, failed, sent_at, id,
             EXISTS (SELECT 1 FROM group_message_copies c WHERE c.message_id = group_messages.id)
      FROM group_messages WHERE group_id = %s ORDER BY sent_at DESC, id DESC LIMIT %s
      """,
      (group_id, limit),
    ).fetchall()
  return [
    {"kind": row[0], "subject": row[1], "text": row[2], "sent_by": row[3], "emailed": row[4], "texted": row[5],
     "skipped": row[6], "failed": row[7], "sent_at": row[8].isoformat(), "id": row[9], "has_copy": row[10]}
    for row in rows
  ]


def keep_copy(connection, message_id: int, email: EmailMessage, bcc: list[str], leader_copy: bool) -> None:
  """Keeps a copy of a sent group email (group_message_copies; the owner's request, 2026-11-18): its From, To,
  Reply-To and Subject, bcc (the addresses it was emailed to, each as a hidden recipient of its own copy),
  leader_copy (the leader also got their own copy), and its plain-text and HTML parts. email is one member's copy
  made with STOP_CODE_PLACEHOLDER as the stop code (the leader's when no member was emailed); a picture shown by
  cid: in the HTML is kept in it as a data: address, since the card files are deleted after a week. A failure is
  logged and goes no further: the email has gone and its Sent row is kept (a savepoint undoes only the copy)."""
  try:
    with connection.transaction():
      _insert_copy(connection, message_id, email, bcc, leader_copy)
  except Exception as problem:
    logger.error("Group message %s: no copy kept: %s", message_id, type(problem).__name__)


def _insert_copy(connection, message_id: int, email: EmailMessage, bcc: list[str], leader_copy: bool) -> None:
  plain = email.get_body(preferencelist=("plain",))
  rich = email.get_body(preferencelist=("html",))
  html = rich.get_content() if rich is not None else None
  if html is not None:
    import base64

    for part in email.walk():
      content_id = (part.get("Content-ID") or "").strip("<> ")
      if content_id and part.get_content_maintype() == "image":
        data = f"data:{part.get_content_type()};base64," + base64.b64encode(part.get_content()).decode()
        html = html.replace(f"cid:{content_id}", data)
  connection.execute(
    """
    INSERT INTO group_message_copies (message_id, from_address, to_address, reply_to, bcc, leader_copy, subject, text, html)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """,
    (message_id, str(email["From"] or ""), str(email["To"] or ""), str(email["Reply-To"] or ""), list(bcc), leader_copy,
     str(email["Subject"] or ""), plain.get_content() if plain is not None else "", html),
  )


def get_copy(group_id: int, message_id: int) -> dict:
  """The copy kept of one sent email of this group (keep_copy), with the Sent table's details of it. Raises
  GroupProblem when the message is not the group's or has no copy (sent before copies were kept)."""
  with connect() as connection:
    row = connection.execute(
      """
      SELECT m.id, m.kind, m.sent_by, m.sent_at, m.emailed, m.texted, m.skipped, m.failed,
             c.from_address, c.to_address, c.reply_to, c.bcc, c.leader_copy, c.subject, c.text, c.html
      FROM group_messages m JOIN group_message_copies c ON c.message_id = m.id
      WHERE m.id = %s AND m.group_id = %s
      """,
      (message_id, group_id),
    ).fetchone()
  if row is None:
    raise GroupProblem("There is no copy of that email (only emails sent since November 18, 2026 have one).")
  return {
    "id": row[0], "kind": row[1], "sent_by": row[2], "sent_at": row[3].isoformat(), "emailed": row[4], "texted": row[5],
    "skipped": row[6], "failed": row[7], "from": row[8], "to": row[9], "reply_to": row[10], "bcc": list(row[11]),
    "leader_copy": row[12], "subject": row[13], "text": row[14], "html": row[15],
    "stop_code_placeholder": STOP_CODE_PLACEHOLDER,
  }
