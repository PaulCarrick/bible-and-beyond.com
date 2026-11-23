"""Signatures (added 2026-11-19 at the owner's request): a name and formatted words to go at the foot of emails,
kept in admin_signatures (migration 054). Not used by any email yet.

Each belongs to the Drupal user who made it (owner_uid); Drupal decides who may see which (the owner only, or
anyone with "administer all signatures and tasks"). The Drupal "Signatures" page runs scripts/manage_signatures.py.
"""

from formatted_text import FormattedTextProblem, clean, one_line
from search import connect

NAME_LIMIT = 200
PREVIEW_LENGTH = 160
MAX_PER_OWNER = 100

COLUMNS = "id, name, html, text, owner_uid, owner_name, created_at, updated_at"


class SignatureProblem(FormattedTextProblem):
  """A signature cannot be kept; the text says why and is fit to show the administrator."""


def _preview(text: str) -> str:
  text = " ".join(text.split())
  return text if len(text) <= PREVIEW_LENGTH else text[: PREVIEW_LENGTH - 1].rstrip() + "…"


def _describe(row) -> dict:
  return {
    "id": row[0], "name": row[1], "html": row[2], "text": row[3], "preview": _preview(row[3]),
    "owner_uid": row[4], "owner_name": row[5], "created_at": row[6].isoformat(), "updated_at": row[7].isoformat(),
  }


def _check(details: dict) -> tuple[str, dict]:
  if not isinstance(details, dict):
    raise SignatureProblem("The signature could not be read.")
  try:
    name = one_line(details.get("name"), "name", NAME_LIMIT)
    words = clean(details.get("signature"), "signature", required=True)
  except FormattedTextProblem as problem:
    raise SignatureProblem(str(problem)) from problem
  return name, words


def list_signatures(owner_uid: int | None = None) -> list[dict]:
  """The signatures by name: one person's (owner_uid), or everyone's."""
  with connect() as connection:
    rows = connection.execute(
      f"SELECT {COLUMNS} FROM admin_signatures WHERE %(owner)s::int IS NULL OR owner_uid = %(owner)s ORDER BY lower(name), id",
      {"owner": owner_uid},
    ).fetchall()
  return [_describe(row) for row in rows]


def get_signature(signature_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM admin_signatures WHERE id = %s", (signature_id,)).fetchone()
  if row is None:
    raise SignatureProblem("That signature was not found. It may have been deleted.")
  return _describe(row)


def create_signature(details: dict, owner_uid: int, owner_name: str) -> dict:
  name, words = _check(details)
  with connect() as connection:
    count = connection.execute("SELECT count(*) FROM admin_signatures WHERE owner_uid = %s", (owner_uid,)).fetchone()[0]
    if count >= MAX_PER_OWNER:
      raise SignatureProblem(f"You can keep up to {MAX_PER_OWNER} signatures. Delete one first.")
    row = connection.execute(
      f"INSERT INTO admin_signatures (name, html, text, owner_uid, owner_name) VALUES (%s, %s, %s, %s, %s) RETURNING {COLUMNS}",
      (name, words["html"], words["text"], owner_uid, " ".join((owner_name or "").split())[:NAME_LIMIT]),
    ).fetchone()
  return _describe(row)


def update_signature(signature_id: int, details: dict) -> dict:
  """Changes the name and words. With new_owner_uid and new_owner_name (an administrator's Owner choice;
  2026-11-23) it moves to that person; the old owner's tasks and group schedules that used it lose it (a signature
  is always its owner's)."""
  name, words = _check(details)
  new_owner = details.get("new_owner_uid")
  with connect() as connection:
    if new_owner is not None:
      new_owner = int(new_owner)
      count = connection.execute(
        "SELECT count(*) FROM admin_signatures WHERE owner_uid = %s AND id <> %s", (new_owner, signature_id)
      ).fetchone()[0]
      if count >= MAX_PER_OWNER:
        raise SignatureProblem(f"That person already has {MAX_PER_OWNER} signatures.")
      connection.execute(
        "UPDATE admin_signatures SET owner_uid = %s, owner_name = %s WHERE id = %s",
        (new_owner, " ".join(str(details.get("new_owner_name") or "").split())[:NAME_LIMIT], signature_id),
      )
      connection.execute("UPDATE admin_tasks SET signature_id = NULL WHERE signature_id = %s AND owner_uid <> %s", (signature_id, new_owner))
      connection.execute(
        """UPDATE group_schedules s SET signature_id = NULL FROM member_groups g
        WHERE s.group_id = g.id AND s.signature_id = %s AND g.owner_uid <> %s""",
        (signature_id, new_owner),
      )
    row = connection.execute(
      f"UPDATE admin_signatures SET name = %s, html = %s, text = %s, updated_at = now() WHERE id = %s RETURNING {COLUMNS}",
      (name, words["html"], words["text"], signature_id),
    ).fetchone()
  if row is None:
    raise SignatureProblem("That signature was not found. It may have been deleted.")
  return _describe(row)


def delete_signature(signature_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"DELETE FROM admin_signatures WHERE id = %s RETURNING {COLUMNS}", (signature_id,)).fetchone()
  if row is None:
    raise SignatureProblem("That signature was not found. It may have been deleted.")
  return _describe(row)
