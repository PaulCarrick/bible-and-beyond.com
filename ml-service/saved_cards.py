"""Saved verse cards (added 2026-11-26 at the owner's request): every card a logged-in member downloads or sends
from "Make your own card" (custom_cards.py) is kept on their My cards page, where they can edit it (open it in the
card maker again; saving changes that card), download it, send it and delete it. A group leader can attach one of
their own saved cards to a group's Send a message in the Drupal admin (groups.py).

- One card per member for each verse, background and own message (saving the same again moves it to the top; a
  card with the member's own message, message_html, is another card from the verse alone); MAX_CARDS a member, the
  oldest dropped past that.
- The picture is kept as drawn (data/saved-cards/<random>.jpg, SAVED_CARDS_FOLDER overrides the folder), with a
  THUMBNAIL-wide copy, so a card still shows after its background is taken out of use. They are served only to the
  member's own session (GET /saved-cards/{id}/image), never in a database, and deleted with the card or the account.
- A Drupal administrator's site account: the one whose users.drupal_uid is theirs (chosen on Site users), else the
  one with their Drupal email address that is not linked to another Drupal account.
"""

import base64
import io
import os
import secrets
from pathlib import Path

import message_cards
from search import connect

MAX_CARDS = 500
THUMBNAIL = 240
_FIELDS = "id, translation, book, chapter, verse, background_id, reference, caption, words, file_name, created_at, message_html"


class SavedCardProblem(Exception):
  """The card cannot be found or used; the text is fit for the member."""

  def __init__(self, message: str, status_code: int = 404):
    super().__init__(message)
    self.status_code = status_code


def folder() -> Path:
  return Path(os.environ.get("SAVED_CARDS_FOLDER") or Path(__file__).resolve().parent / "data" / "saved-cards")


def picture_path(file_name: str) -> Path:
  return folder() / Path(file_name).name


def thumbnail_path(file_name: str) -> Path:
  return folder() / (Path(file_name).stem + "-thumbnail.jpg")


def _describe(row) -> dict:
  version = Path(row[9]).stem[:8]
  return {
    "id": row[0],
    "translation": row[1],
    "book": row[2],
    "chapter": row[3],
    "verse": row[4],
    "background": row[5],
    "reference": row[6],
    "caption": row[7],
    "words": row[8],
    "image": f"/saved-cards/{row[0]}/image?v={version}",
    "thumbnail": f"/saved-cards/{row[0]}/thumbnail?v={version}",
    "created_at": row[10].isoformat(),
    # The member's own message as cleaned HTML (it is the card's words), or None for the verse's own words.
    "message_html": row[11],
  }


def _write_files(picture) -> str:
  """Saves the drawn card and its thumbnail under a new random name; returns the name."""
  target = folder()
  target.mkdir(parents=True, exist_ok=True)
  name = secrets.token_urlsafe(18) + ".jpg"
  temporary = target / f".{name}.new"
  picture.save(temporary, "JPEG", quality=message_cards.JPEG_QUALITY, optimize=True, progressive=True)
  os.replace(temporary, picture_path(name))
  small = picture.copy()
  small.thumbnail((THUMBNAIL, THUMBNAIL * 2))
  small.convert("RGB").save(thumbnail_path(name), "JPEG", quality=80, optimize=True)
  return name


def _remove_files(file_name: str) -> None:
  picture_path(file_name).unlink(missing_ok=True)
  thumbnail_path(file_name).unlink(missing_ok=True)


def keep(user_id: int, found: dict, background_id: str, picture, card_id: int | None = None) -> dict:
  """Keeps a drawn card (found: custom_cards' verse, with message_html when the member wrote their own message;
  picture: the Pillow card) for the member. card_id: the saved card being edited, which this replaces; otherwise the
  member's card of that verse, background and message is replaced, or a new one made. Returns the card."""
  verse = found["verse"]
  message_html = found.get("message_html")
  key = (verse["translation"], verse["book"], verse["chapter"], verse["verse"], background_id)
  name = _write_files(picture)
  old_files = []
  try:
    with connect() as connection:
      if card_id is not None:
        row = connection.execute("SELECT file_name FROM saved_cards WHERE id = %s AND user_id = %s", (card_id, user_id)).fetchone()
        if row is None:
          raise SavedCardProblem("That card is not one of yours.")
        old_files.append(row[0])
      # Another card of the same verse, background and message goes: the member keeps one of each.
      clash = connection.execute(
        """SELECT id, file_name FROM saved_cards WHERE user_id = %s AND translation = %s AND book = %s AND chapter = %s
           AND verse = %s AND background_id = %s AND message_html IS NOT DISTINCT FROM %s""",
        (user_id, *key, message_html),
      ).fetchone()
      if clash and clash[0] != card_id:
        if card_id is None:
          card_id = clash[0]
        else:
          connection.execute("DELETE FROM saved_cards WHERE id = %s", (clash[0],))
        old_files.append(clash[1])
      values = (*key, found["reference"], found["caption"], found["text"], name, message_html)
      if card_id is None:
        row = connection.execute(
          f"""INSERT INTO saved_cards (user_id, translation, book, chapter, verse, background_id, reference, caption, words, file_name, message_html)
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {_FIELDS}""",
          (user_id, *values),
        ).fetchone()
      else:
        row = connection.execute(
          f"""UPDATE saved_cards SET translation = %s, book = %s, chapter = %s, verse = %s, background_id = %s,
              reference = %s, caption = %s, words = %s, file_name = %s, message_html = %s, created_at = now()
              WHERE id = %s AND user_id = %s RETURNING {_FIELDS}""",
          (*values, card_id, user_id),
        ).fetchone()
      # The oldest past MAX_CARDS go.
      extra = connection.execute(
        "SELECT id, file_name FROM saved_cards WHERE user_id = %s ORDER BY created_at DESC, id DESC OFFSET %s",
        (user_id, MAX_CARDS),
      ).fetchall()
      for extra_id, extra_file in extra:
        connection.execute("DELETE FROM saved_cards WHERE id = %s", (extra_id,))
        old_files.append(extra_file)
  except Exception:
    _remove_files(name)
    raise
  for old in set(old_files) - {name}:
    _remove_files(old)
  return _describe(row)


def list_cards(user_id: int) -> list[dict]:
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {_FIELDS} FROM saved_cards WHERE user_id = %s ORDER BY created_at DESC, id DESC", (user_id,)
    ).fetchall()
  return [_describe(row) for row in rows]


def get_card(user_id: int, card_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {_FIELDS} FROM saved_cards WHERE id = %s AND user_id = %s", (card_id, user_id)).fetchone()
  if row is None:
    raise SavedCardProblem("That card is not one of yours.")
  card = _describe(row)
  card["file_name"] = row[9]
  return card


def card_file(user_id: int, card_id: int, thumbnail: bool = False) -> Path:
  card = get_card(user_id, card_id)
  path = thumbnail_path(card["file_name"]) if thumbnail else picture_path(card["file_name"])
  if not path.is_file():
    raise SavedCardProblem("That card's picture is missing.")
  return path


def delete(user_id: int, card_id: int) -> None:
  with connect() as connection:
    row = connection.execute("DELETE FROM saved_cards WHERE id = %s AND user_id = %s RETURNING file_name", (card_id, user_id)).fetchone()
  if row is None:
    raise SavedCardProblem("That card is not one of yours.")
  _remove_files(row[0])


def remove_all(connection, user_id: int) -> None:
  """The files of a member's cards, when the account is deleted (the rows go with it, ON DELETE CASCADE)."""
  for (file_name,) in connection.execute("SELECT file_name FROM saved_cards WHERE user_id = %s", (user_id,)).fetchall():
    _remove_files(file_name)


def card_for_sending(user_id: int, card_id: int) -> message_cards.MessageCard:
  """A saved card copied to the message cards (a random public name, kept a week), so an email can carry it and a
  text (MMS) fetch it."""
  from PIL import Image

  with Image.open(card_file(user_id, card_id)) as picture:
    picture.load()
    return message_cards.save_card(picture.convert("RGB"))


# --- the Drupal administrator's site account ---------------------------------------------------------------


def account_for_admin(drupal_uid: int, email: str | None) -> dict | None:
  """The site account of a Drupal account: the one linked to it on Site users, else the open one with the same
  email address that is not linked to another Drupal account. {id, name, email} or None."""
  with connect() as connection:
    row = connection.execute(
      """
      SELECT id, NULLIF(concat_ws(' ', first_name, last_name), ''), email FROM users
      WHERE disabled_at IS NULL AND (drupal_uid = %(uid)s
        OR (drupal_uid IS NULL AND %(email)s <> '' AND lower(email) = lower(%(email)s)))
      ORDER BY drupal_uid IS NULL, id LIMIT 1
      """,
      {"uid": int(drupal_uid), "email": (email or "").strip()},
    ).fetchone()
  if row is None:
    return None
  return {"id": row[0], "name": row[1] or row[2] or "A member", "email": row[2]}


def admin_cards(drupal_uid: int, email: str | None, limit: int = 30) -> dict:
  """For the Drupal admin: the administrator's site account and its newest cards, each with its thumbnail as a
  data: address (the admin site cannot fetch the member-only addresses)."""
  account = account_for_admin(drupal_uid, email)
  cards = []
  if account:
    with connect() as connection:
      rows = connection.execute(
        f"SELECT {_FIELDS} FROM saved_cards WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
        (account["id"], limit),
      ).fetchall()
    for row in rows:
      path = thumbnail_path(row[9])
      if not path.is_file():
        continue
      card = _describe(row)
      cards.append({
        "id": card["id"],
        "caption": card["caption"],
        "words": card["words"],
        "created_at": card["created_at"],
        "thumbnail": "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode(),
      })
  return {"account": account, "cards": cards}
