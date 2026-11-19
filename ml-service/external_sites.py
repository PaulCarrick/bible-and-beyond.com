"""External sites (added 2026-11-19 at the owner's request, first for the Kindle web reader): a shared list of sites the
administrators open from the Drupal "External sites" page, kept in admin_external_sites (migration 059). Each has a
name, an address, notes and an optional sign-in address (a Sign in button beside Open: our page cannot see whether
one is signed in to another site, since browsers keep each site's cookies and pages to itself).

Drupal opens a site in its own browser window, never in a frame: Amazon's sign-in page refuses to be shown inside
another site (X-Frame-Options: SAMEORIGIN), and browsers keep a framed site's cookies and storage apart from the same
site opened normally, so a framed reader would stay signed out. Only http(s) addresses are kept, so a link can never
run script (javascript:) or open a local file.
"""

from urllib.parse import urlsplit

from formatted_text import FormattedTextProblem, one_line
from search import connect

NAME_LIMIT = 200
ADDRESS_LIMIT = 2000
NOTES_LIMIT = 2000
MAX_SITES = 200

COLUMNS = "id, name, address, notes, created_by, created_at, updated_at, sign_in_address"


class ExternalSiteProblem(FormattedTextProblem):
  """A site cannot be kept; the text says why and is fit to show the administrator."""


def _describe(row) -> dict:
  return {
    "id": row[0], "name": row[1], "address": row[2], "host": urlsplit(row[2]).hostname or "", "notes": row[3],
    "created_by": row[4], "created_at": row[5].isoformat(), "updated_at": row[6].isoformat(), "sign_in_address": row[7],
  }


def check_address(value, what: str = "address") -> str:
  """An absolute http or https address with a host, spaces trimmed. "read.amazon.com" alone gets https://."""
  if not isinstance(value, str) or not value.strip():
    raise ExternalSiteProblem(f"The {what} is needed, such as https://read.amazon.com.")
  address = value.strip()
  if "://" not in address and not address.lower().startswith(("javascript:", "data:", "file:", "mailto:")):
    address = "https://" + address
  if len(address) > ADDRESS_LIMIT:
    raise ExternalSiteProblem(f"The {what} can be at most {ADDRESS_LIMIT} characters.")
  if any(character.isspace() or ord(character) < 32 for character in address):
    raise ExternalSiteProblem(f"The {what} cannot contain spaces.")
  parts = urlsplit(address)
  if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
    raise ExternalSiteProblem(f"The {what} must be a web address starting with https:// (or http://).")
  if parts.username or parts.password:
    raise ExternalSiteProblem(f"Leave the user name and password out of the {what}: sign in on the site itself.")
  return address


def _check(details: dict) -> tuple[str, str, str, str]:
  if not isinstance(details, dict):
    raise ExternalSiteProblem("The site could not be read.")
  try:
    name = one_line(details.get("name"), "name", NAME_LIMIT)
  except FormattedTextProblem as problem:
    raise ExternalSiteProblem(str(problem)) from problem
  notes = details.get("notes") or ""
  if not isinstance(notes, str):
    raise ExternalSiteProblem("The notes could not be read.")
  notes = notes.replace("\r\n", "\n").strip()
  if len(notes) > NOTES_LIMIT:
    raise ExternalSiteProblem(f"The notes can be at most {NOTES_LIMIT} characters.")
  if any(ord(character) < 32 and character not in "\n\t" for character in notes):
    raise ExternalSiteProblem("The notes have characters that cannot be kept.")
  sign_in = details.get("sign_in_address") or ""
  sign_in = check_address(sign_in, "sign-in address") if isinstance(sign_in, str) and sign_in.strip() else ""
  return name, check_address(details.get("address")), notes, sign_in


def list_sites() -> list[dict]:
  with connect() as connection:
    rows = connection.execute(f"SELECT {COLUMNS} FROM admin_external_sites ORDER BY lower(name), id").fetchall()
  return [_describe(row) for row in rows]


def get_site(site_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"SELECT {COLUMNS} FROM admin_external_sites WHERE id = %s", (site_id,)).fetchone()
  if row is None:
    raise ExternalSiteProblem("That site was not found. It may have been deleted.")
  return _describe(row)


def create_site(details: dict, created_by: str) -> dict:
  name, address, notes, sign_in = _check(details)
  with connect() as connection:
    if connection.execute("SELECT count(*) FROM admin_external_sites").fetchone()[0] >= MAX_SITES:
      raise ExternalSiteProblem(f"There can be up to {MAX_SITES} sites. Delete one first.")
    row = connection.execute(
      f"INSERT INTO admin_external_sites (name, address, notes, sign_in_address, created_by) VALUES (%s, %s, %s, %s, %s) RETURNING {COLUMNS}",
      (name, address, notes, sign_in, " ".join((created_by or "").split())[:NAME_LIMIT]),
    ).fetchone()
  return _describe(row)


def update_site(site_id: int, details: dict) -> dict:
  name, address, notes, sign_in = _check(details)
  with connect() as connection:
    row = connection.execute(
      f"""UPDATE admin_external_sites SET name = %s, address = %s, notes = %s, sign_in_address = %s, updated_at = now()
      WHERE id = %s RETURNING {COLUMNS}""",
      (name, address, notes, sign_in, site_id),
    ).fetchone()
  if row is None:
    raise ExternalSiteProblem("That site was not found. It may have been deleted.")
  return _describe(row)


def delete_site(site_id: int) -> dict:
  with connect() as connection:
    row = connection.execute(f"DELETE FROM admin_external_sites WHERE id = %s RETURNING {COLUMNS}", (site_id,)).fetchone()
  if row is None:
    raise ExternalSiteProblem("That site was not found. It may have been deleted.")
  return _describe(row)
