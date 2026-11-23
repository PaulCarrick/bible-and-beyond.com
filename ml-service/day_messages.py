"""A message to the people scheduled on one date (added 2026-11-23 at the owner's request): "Message a day" on the
Drupal Scheduled tasks page. Choose a date (from the dates that have something scheduled), untick anyone to leave
out, write the message in the editor and choose a signature. Each person gets it the way they chose on My account
(email to a confirmed address, text, or both; scheduled_tasks._ways), and a failed text falls back to email as task
reminders do. [FIRST_NAME], [LAST_NAME] and [FULL_NAME] are filled in for each person (scheduled_tasks.fill_names).
Nothing is kept but the Drupal log line; the message is not stored.

The dates and people are those of the tasks the Drupal user may see (owner_uid; None for an administrator).
"""

import logging
import time
from datetime import date
from email.message import EmailMessage
from html import escape

import sms
from admin_tasks import TaskProblem
from contact import MailUnavailable, load_mail_settings, send_email
from formatted_text import FormattedTextProblem, clean, one_line
from scheduled_tasks import _user_label, _ways, date_label, fill_names
from search import connect
from site_settings import get_public_settings

logger = logging.getLogger(__name__)

PAUSE_SECONDS = 0.5
SUBJECT_LIMIT = 200
MAX_PEOPLE = 300


def dates(owner_uid: int | None = None, today: date | None = None) -> list[dict]:
  """The dates from today on that have something scheduled, soonest first: {value, label, people}."""
  today = today or date.today()
  with connect() as connection:
    rows = connection.execute(
      """
      SELECT s.on_date, count(DISTINCT s.user_id) FROM admin_scheduled_tasks s JOIN admin_tasks t ON t.id = s.task_id
      WHERE s.on_date >= %(today)s AND (%(owner)s::int IS NULL OR t.owner_uid = %(owner)s)
      GROUP BY s.on_date ORDER BY s.on_date
      """,
      {"today": today, "owner": owner_uid},
    ).fetchall()
  return [{"value": row[0].isoformat(), "label": date_label(row[0]), "people": row[1]} for row in rows]


def people(on_date: date, owner_uid: int | None = None) -> list[dict]:
  """The people scheduled on that date, once each, by name: {id, label, tasks (their task names), reachable}."""
  with connect() as connection:
    rows = connection.execute(
      """
      SELECT u.id, COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), ''), COALESCE(u.email, u.phone, ''),
             array_agg(t.name ORDER BY lower(t.name)), u.disabled_at IS NULL
      FROM admin_scheduled_tasks s JOIN admin_tasks t ON t.id = s.task_id JOIN users u ON u.id = s.user_id
      WHERE s.on_date = %(day)s AND (%(owner)s::int IS NULL OR t.owner_uid = %(owner)s)
      GROUP BY u.id ORDER BY lower(COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), u.email, u.phone)), u.id
      """,
      {"day": on_date, "owner": owner_uid},
    ).fetchall()
  return [{"id": row[0], "label": _user_label(row[1], row[2]), "tasks": list(row[3]), "open": row[4]} for row in rows]


def _signature(signature_id, sender_uid: int) -> dict | None:
  if signature_id in (None, ""):
    return None
  try:
    signature_id = int(signature_id)
  except (TypeError, ValueError) as error:
    raise TaskProblem("Choose one of your signatures, or no signature.") from error
  with connect() as connection:
    row = connection.execute(
      "SELECT html, text FROM admin_signatures WHERE id = %s AND owner_uid = %s", (signature_id, sender_uid)
    ).fetchone()
  if row is None:
    raise TaskProblem("That signature is not one of yours (it may have been deleted).")
  return {"html": row[0], "text": row[1]}


def compose(settings: dict, message: dict, person: dict) -> EmailMessage:
  """One person's email: To them, Reply-To the sender, the message with their name filled in, the signature and a
  one-line foot."""
  first, last = person["first_name"], person["last_name"]
  html = fill_names(message["html"], first, last, html=True)
  text = fill_names(message["text"], first, last)
  signature = message.get("signature")
  if signature:
    html += signature["html"]
    text += f"\n\n{signature['text']}"
  title = get_public_settings()["title"]
  foot = f"Sent by {message['sender_name'] or title} to the people scheduled on {message['day_label']}, through {title}."
  email = EmailMessage()
  email["Subject"] = fill_names(message["subject"], first, last)
  email["From"] = settings["from_address"]
  email["To"] = person["address"]
  if message.get("sender_email"):
    email["Reply-To"] = message["sender_email"]
  email.set_content(f"{text}\n\n--\n{foot}\n")
  email.add_alternative(f"<html><body>{html}<hr><p>{escape(foot)}</p></body></html>", subtype="html")
  return email


def send(details: dict, sender_uid: int, owner_uid: int | None = None) -> dict:
  """Sends the message to the chosen people of a date. details: on_date, user_ids, subject, message ({html} or
  {text}), signature_id, sender_name, sender_email. Returns {sent: [{label, how}], not_sent: [{label, why}]}."""
  if not isinstance(details, dict):
    raise TaskProblem("The message could not be read.")
  try:
    on_date = date.fromisoformat(str(details.get("on_date") or ""))
  except ValueError as error:
    raise TaskProblem("Choose a date.") from error
  try:
    subject = one_line(details.get("subject"), "subject", SUBJECT_LIMIT)
    words = clean(details.get("message"), "message", required=True)
  except FormattedTextProblem as problem:
    raise TaskProblem(str(problem)) from problem
  chosen = {int(user_id) for user_id in (details.get("user_ids") or []) if str(user_id).isdigit()}
  if not chosen:
    raise TaskProblem("Tick at least one person to send it to.")
  if len(chosen) > MAX_PEOPLE:
    raise TaskProblem(f"Send to at most {MAX_PEOPLE} people at a time.")
  scheduled = {person["id"]: person for person in people(on_date, owner_uid)}
  if not chosen <= set(scheduled):
    raise TaskProblem("Someone ticked is not scheduled on that date (the list may have changed). Choose the date again.")
  message = {
    "subject": subject, "html": words["html"], "text": words["text"], "day_label": date_label(on_date),
    "signature": _signature(details.get("signature_id"), sender_uid),
    "sender_name": " ".join(str(details.get("sender_name") or "").split())[:200],
    "sender_email": str(details.get("sender_email") or "").strip()[:320],
  }
  with connect() as connection:
    rows = connection.execute(
      """SELECT id, first_name, last_name, email, email_verified_at IS NOT NULL, disabled_at IS NOT NULL
      FROM users WHERE id = ANY(%s)""",
      (sorted(chosen),),
    ).fetchall()
  settings = None
  result = {"sent": [], "not_sent": []}
  for index, (user_id, first_name, last_name, address, confirmed, closed) in enumerate(sorted(rows, key=lambda row: scheduled[row[0]]["label"].lower())):
    label = scheduled[user_id]["label"]
    if index:
      time.sleep(PAUSE_SECONDS)
    by_email, number, problem = _ways(user_id, address, confirmed, closed)
    if problem is not None:
      result["not_sent"].append({"label": label, "why": problem.removeprefix("Not sent: ")})
      continue
    person = {"first_name": first_name, "last_name": last_name, "address": address}

    reasons = []

    def email_it() -> bool:
      nonlocal settings
      try:
        settings = settings or load_mail_settings()
        send_email(settings, compose(settings, message, person))
        return True
      except MailUnavailable as failure:
        reasons.append(f"the email: {failure}")
        return False
      except Exception as failure:
        logger.error("A day message to user %s was not emailed: %s", user_id, type(failure).__name__)
        reasons.append("the email could not be sent (the details are in the server's log)")
        return False

    went = []
    if by_email and email_it():
      went.append("email")
    if number:
      words_of_text = fill_names(f"{subject}: {message['text']}", first_name, last_name)
      try:
        if sms.send_text(number, sms.compose(words_of_text)):
          went.append("text")
        else:
          reasons.append("the text could not be sent")
      except Exception as failure:
        logger.error("A day message to user %s was not texted: %s", user_id, type(failure).__name__)
        reasons.append("the text could not be sent")
      # Texts only and the text failed: by email instead, if their address is confirmed (as task reminders).
      if "text" not in went and not by_email and address and confirmed and email_it():
        went.append("email")
    if went:
      result["sent"].append({"label": label, "how": " and ".join(went)})
    else:
      result["not_sent"].append({"label": label, "why": "; ".join(reasons) or "it could not be sent"})
  return result
