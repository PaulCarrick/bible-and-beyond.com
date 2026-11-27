"""The sign-up sheet PDF of a group for a period (the owner's request, 2026-11-27), modelled on their paper "After
Church Fellowship Time" form: a title, then one block per date with a row per place to fill, and the leader's notes
at the foot.

- The tasks are the group's own (admin_tasks.group_id, migration 075; a task with no group is on no sheet), in their
  sheet order then by name. A date gets a block when any of them falls on it, by each task's own recurrence.
- Blank: each task has as many rows as it expects (expected_occurrences), numbered when more than one ("Baked Goods
  1", "Baked Goods 2").
- Filled in: the people scheduled (admin_scheduled_tasks) with their name, note, email and phone, then blank rows up
  to the number expected; someone not confirmed yet is marked so. A long block runs onto the next page.
- The notes (cleaned HTML from the editor) go at the foot with no label, and are left off when empty.

The title is the group's Description (member_groups.headline, migration 076), else its name. The notes are kept for
next time only when "Save this note" is ticked (save_notes), for this report and group (report_notes, migration 077).
The layout (letter landscape, the yellow Notes and blue Phone columns) is the one the owner approved.
"""

import base64
import re
from datetime import date, timedelta
from html import escape, unescape
from html.parser import HTMLParser
from io import BytesIO

from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, Paragraph

import admin_tasks
from formatted_text import FormattedTextProblem, clean, one_line
from search import connect

WIDTH, HEIGHT = landscape(letter)
MARGIN = 0.5 * 72
YELLOW, BLUE, LINE, ORANGE = HexColor("#f4ee98"), HexColor("#b4c6d6"), HexColor("#9a9a9a"), HexColor("#a05a00")
COLUMNS = {"task": MARGIN + 24, "name": MARGIN + 160, "notes": MARGIN + 305, "email": MARGIN + 440, "phone": MARGIN + 590,
           "end": WIDTH - MARGIN}
# Where each column's writing line ends (a gap before the next column).
LINE_ENDS = {"name": COLUMNS["notes"] - 12, "notes": COLUMNS["email"] - 26, "email": COLUMNS["phone"] - 14, "phone": COLUMNS["end"] - 4}
ROW = 14.5
TITLE_GAP = 30
BLOCK_HEAD = 8
BLOCK_FOOT = 19
MAX_DAYS = 366
# How low the notes may go (the rows keep the half-inch margin).
NOTES_BOTTOM = 0.3 * 72
TITLE_LIMIT = 120
NOTES_LIMIT = 20000


class SheetProblem(Exception):
  """A sheet that cannot be made; the text is fit to show the administrator."""


# --- the data ---------------------------------------------------------------------------------------------

# The notes saved for this report and group (report_notes, migration 077), '' when none.
REPORT = "sign_up_sheet"
_SAVED_NOTES = f"""COALESCE((SELECT n.notes_html FROM report_notes n WHERE n.report = '{REPORT}' AND n.group_id = g.id), '')"""



def _group(connection, group_id: int, owner_uid: int | None) -> dict:
  row = connection.execute(
    f"SELECT id, name, owner_uid, owner_name, headline, {_SAVED_NOTES} FROM member_groups g WHERE id = %s", (group_id,)
  ).fetchone()
  if row is None or (owner_uid is not None and row[2] != owner_uid):
    raise SheetProblem("That group was not found.")
  return {"id": row[0], "name": row[1], "owner_uid": row[2], "owner_name": row[3], "title": row[4] or row[1], "sheet_notes_html": row[5]}


def groups(owner_uid: int | None = None) -> list[dict]:
  """The groups to choose from (one leader's, or everyone's), by name, each with its sheet title (its Description,
  else its name) and its remembered notes."""
  with connect() as connection:
    rows = connection.execute(
      f"""SELECT id, name, owner_uid, owner_name, headline, {_SAVED_NOTES} FROM member_groups g
      WHERE %(owner)s::int IS NULL OR owner_uid = %(owner)s ORDER BY lower(name), id""",
      {"owner": owner_uid},
    ).fetchall()
  # title: the group's Description (headline; migration 076), else its name.
  return [{"id": row[0], "name": row[1], "owner_uid": row[2], "owner_name": row[3], "title": row[4] or row[1],
           "sheet_notes_html": row[5]} for row in rows]


def _tasks(connection, group_id: int) -> list[dict]:
  ids = [row[0] for row in connection.execute(
    "SELECT id FROM admin_tasks WHERE group_id = %s ORDER BY sheet_order, lower(name), id", (group_id,)
  ).fetchall()]
  tasks = [admin_tasks.get_task(task_id) for task_id in ids]
  for task in tasks:
    task["rule"] = {**task, "first_date": date.fromisoformat(task["first_date"])}
  return tasks


def _people(connection, task_ids: list[int], start: date, end: date) -> dict:
  """The scheduled people by (task id, date): confirmed first, then in the order they were added."""
  rows = connection.execute(
    """SELECT s.task_id, s.on_date, COALESCE(NULLIF(trim(concat_ws(' ', u.first_name, u.last_name)), ''), u.email, u.phone, ''),
              s.note_text, COALESCE(u.email, ''), COALESCE(u.phone, ''), s.confirmed
    FROM admin_scheduled_tasks s JOIN users u ON u.id = s.user_id
    WHERE s.task_id = ANY(%s) AND s.on_date BETWEEN %s AND %s
    ORDER BY s.task_id, s.on_date, s.confirmed DESC, s.id""",
    (task_ids, start, end),
  ).fetchall()
  people = {}
  for task_id, day, name, note, email, phone, confirmed in rows:
    note = " ".join((note or "").split())
    people.setdefault((task_id, day), []).append(
      {"name": name, "notes": note, "email": email, "phone": phone, "confirmed": confirmed}
    )
  return people


def sheet_dates(tasks: list[dict], start: date, end: date, people: dict | None) -> list[tuple[date, list[dict]]]:
  """Each date in the period that any task falls on, with its rows: {task (the label), name, notes, email, phone,
  confirmed} (only task for a blank row)."""
  dates = []
  day = start
  while day <= end:
    rows = []
    for task in tasks:
      if not admin_tasks.occurs_on(task["rule"], day):
        continue
      filled = (people or {}).get((task["id"], day), [])
      count = max(task["expected_occurrences"] or 1, len(filled))
      for index in range(count):
        label = f"{task['name']} {index + 1}" if count > 1 else task["name"]
        rows.append({"task": label, **(filled[index] if index < len(filled) else {})})
    if rows:
      dates.append((day, rows))
    day += timedelta(days=1)
  return dates


# --- the notes ---------------------------------------------------------------------------------------------


_FONTS = {"georgia": "Times", "times": "Times", "serif": "Times", "courier": "Courier", "monospace": "Courier"}


def _font_family(value: str) -> str:
  lowered = value.lower()
  for key, font in _FONTS.items():
    if key in lowered and not (key == "serif" and "sans" in lowered):
      return font
  return "Helvetica"


class _NotesReader(HTMLParser):
  """Turns the editor's cleaned HTML into reportlab paragraph markup: one entry per paragraph, heading or list point
  (as (markup, kind))."""

  def __init__(self):
    super().__init__(convert_charrefs=True)
    self.blocks: list[tuple[str, str]] = []
    self.current: list[str] = []
    self.kind = "p"
    self.closers: list[str] = []
    self.lists: list[list] = []

  def _flush(self):
    text = "".join(self.current).strip()
    if text and re.sub(r"<[^>]+>", "", text).strip():
      self.blocks.append((text, self.kind))
    self.current = []

  def handle_starttag(self, tag, attrs):
    attrs = dict(attrs)
    if tag in ("p", "h1", "h2", "h3", "h4", "blockquote", "div"):
      self._flush()
      self.kind = tag if tag in ("h1", "h2", "h3", "h4") else "p"
    elif tag in ("ul", "ol"):
      self._flush()
      self.lists.append([tag, 0])
    elif tag == "li":
      self._flush()
      if self.lists:
        self.lists[-1][1] += 1
        bullet = "•" if self.lists[-1][0] == "ul" else f"{self.lists[-1][1]}."
      else:
        bullet = "•"
      self.kind = "li"
      self.current.append(f"{bullet}&nbsp;&nbsp;")
    elif tag == "br":
      self.current.append("<br/>")
    elif tag in ("strong", "b"):
      self.current.append("<b>"); self.closers.append("</b>")
    elif tag in ("em", "i"):
      self.current.append("<i>"); self.closers.append("</i>")
    elif tag == "u":
      self.current.append("<u>"); self.closers.append("</u>")
    elif tag in ("s", "strike", "del"):
      self.current.append("<strike>"); self.closers.append("</strike>")
    elif tag == "a":
      href = attrs.get("href") or ""
      if href.startswith(("http://", "https://", "mailto:")):
        self.current.append(f'<a href="{escape(href)}" color="#1a6ebd">'); self.closers.append("</a>")
      else:
        self.closers.append("")
    elif tag == "span":
      style = attrs.get("style") or ""
      parts = []
      family = re.search(r"font-family:\s*([^;]+)", style)
      size = re.search(r"font-size:\s*(\d+(?:\.\d+)?)px", style)
      colour = re.search(r"(?<!-)color:\s*(#[0-9a-fA-F]{6})", style)
      if family:
        parts.append(f'name="{_font_family(family.group(1))}"')
      if size:
        parts.append(f'size="{round(float(size.group(1)) * 0.75, 1)}"')
      if colour:
        parts.append(f'color="{colour.group(1)}"')
      if parts:
        self.current.append(f"<font {' '.join(parts)}>"); self.closers.append("</font>")
      else:
        self.closers.append("")

  def handle_endtag(self, tag):
    if tag in ("p", "h1", "h2", "h3", "h4", "blockquote", "div", "li"):
      self._flush()
      self.kind = "p"
    elif tag in ("ul", "ol"):
      self._flush()
      if self.lists:
        self.lists.pop()
    elif tag in ("strong", "b", "em", "i", "u", "s", "strike", "del", "a", "span"):
      if self.closers:
        self.current.append(self.closers.pop())

  def handle_data(self, data):
    self.current.append(escape(data, quote=False))

  def close(self):
    super().close()
    self.current.extend(reversed(self.closers))
    self.closers = []
    self._flush()


def notes_paragraphs(html: str) -> list[Paragraph]:
  if not (html or "").strip():
    return []
  reader = _NotesReader()
  reader.feed(html)
  reader.close()
  styles = {
    "p": ParagraphStyle("notes", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=5),
    "li": ParagraphStyle("notes-point", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=3, leftIndent=14, firstLineIndent=-10),
    "h1": ParagraphStyle("notes-h1", fontName="Helvetica-Bold", fontSize=14, leading=18, spaceAfter=5),
    "h2": ParagraphStyle("notes-h2", fontName="Helvetica-Bold", fontSize=13, leading=17, spaceAfter=5),
    "h3": ParagraphStyle("notes-h3", fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceAfter=4),
    "h4": ParagraphStyle("notes-h4", fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceAfter=4),
  }
  paragraphs = []
  for markup, kind in reader.blocks:
    try:
      paragraphs.append(Paragraph(markup, styles.get(kind, styles["p"])))
    except Exception:  # Markup reportlab cannot read: keep the words.
      paragraphs.append(Paragraph(escape(unescape(re.sub(r"<[^>]+>", "", markup))), styles["p"]))
  return paragraphs


# --- drawing -----------------------------------------------------------------------------------------------


def _fit(text: str, font: str, size: float, width: float) -> str:
  """The text cut with … to fit the width."""
  text = text or ""
  if stringWidth(text, font, size) <= width:
    return text
  while text and stringWidth(text + "…", font, size) > width:
    text = text[:-1]
  return text.rstrip() + "…"


def _day_heading(day: date) -> str:
  return f"{day.strftime('%A, %B')} {day.day}".upper()


class _Sheet:
  def __init__(self, title: str):
    self.buffer = BytesIO()
    self.canvas = canvas.Canvas(self.buffer, pagesize=(WIDTH, HEIGHT))
    self.canvas.setTitle(title)
    self.title = title
    self.y = self._heading()

  def _heading(self) -> float:
    self.canvas.setFont("Helvetica-Bold", 16)
    self.canvas.drawString(MARGIN, HEIGHT - MARGIN - 6, _fit(self.title, "Helvetica-Bold", 16, WIDTH - 2 * MARGIN))
    return HEIGHT - MARGIN - TITLE_GAP

  def new_page(self):
    self.canvas.showPage()
    self.y = self._heading()

  def block(self, day: date, rows: list[dict], blank: bool):
    """One date. A block that does not fit goes to the next page; one longer than a page runs on, its heading
    repeated with "(continued)"."""
    room_on_new_page = HEIGHT - MARGIN - TITLE_GAP - MARGIN - BLOCK_HEAD - BLOCK_FOOT - 4
    whole = ROW * len(rows) + BLOCK_HEAD + 4
    if self.y - whole < MARGIN and whole <= room_on_new_page:
      self.new_page()
    continued = False
    while rows:
      fits = max(1, int((self.y - MARGIN - BLOCK_HEAD - 4) // ROW))
      if fits < 2 and len(rows) > 1:
        self.new_page()
        continue
      part, rows = rows[:fits], rows[fits:]
      self._part(day, part, blank, continued)
      continued = True
      if rows:
        self.new_page()

  def _part(self, day: date, rows: list[dict], blank: bool, continued: bool):
    c, y = self.canvas, self.y
    heading = _day_heading(day) + (" (CONTINUED)" if continued else "")
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, y, heading)
    c.setStrokeColor(black); c.setLineWidth(0.8)
    c.line(MARGIN, y - 3, max(COLUMNS["name"] - 12, MARGIN + stringWidth(heading, "Helvetica-Bold", 12)), y - 3)
    c.setFont("Helvetica-Bold", 10)
    for key, label in (("name", "Name"), ("notes", "Notes"), ("email", "Email"), ("phone", "Phone (Text)")):
      c.drawString(COLUMNS[key], y, label)
    top = y - BLOCK_HEAD
    bottom = top - ROW * len(rows) - 4
    c.setFillColor(YELLOW); c.rect(COLUMNS["notes"], bottom, COLUMNS["email"] - COLUMNS["notes"] - 20, top - bottom, stroke=0, fill=1)
    c.setFillColor(BLUE); c.rect(COLUMNS["phone"] - 6, bottom, COLUMNS["end"] - COLUMNS["phone"] + 6, top - bottom, stroke=0, fill=1)
    c.setFillColor(black)
    for index, row in enumerate(rows):
      base = top - ROW * (index + 1)
      c.setFont("Helvetica-Bold", 9)
      c.drawString(COLUMNS["task"], base + 3, _fit(row["task"], "Helvetica-Bold", 9, COLUMNS["name"] - COLUMNS["task"] - 8))
      c.setStrokeColor(LINE); c.setLineWidth(0.5)
      for key, end in LINE_ENDS.items():
        c.line(COLUMNS[key], base, end, base)
      if blank or not row.get("name"):
        continue
      mark = not row.get("confirmed")
      for key in ("name", "notes", "email", "phone"):
        width = LINE_ENDS[key] - COLUMNS[key] - 4 - (52 if key == "name" and mark else 0)
        c.setFont("Helvetica", 9.5)
        c.drawString(COLUMNS[key] + 2, base + 3, _fit(row.get(key) or "", "Helvetica", 9.5, width))
      if mark:
        c.setFont("Helvetica-Oblique", 7); c.setFillColor(ORANGE)
        c.drawRightString(LINE_ENDS["name"] - 2, base + 3, "not confirmed")
        c.setFillColor(black)
    self.y = bottom - BLOCK_FOOT

  def notes(self, paragraphs: list[Paragraph]):
    """The notes at the foot: a thin rule, then the paragraphs (no label), running onto more pages if long."""
    if not paragraphs:
      return
    width = WIDTH - 2 * MARGIN
    # Short notes may use some of the bottom margin, so that they stay on the page with the last date.
    bottom = NOTES_BOTTOM
    total = sum(paragraph.wrap(width, HEIGHT)[1] + paragraph.style.spaceAfter for paragraph in paragraphs)
    room_on_new_page = HEIGHT - MARGIN - TITLE_GAP - bottom
    first = paragraphs[0].wrap(width, HEIGHT)[1] + 12
    # Kept together: notes that fit on a page of their own but not here go to the next page whole.
    if self.y - first < bottom or (self.y - total < bottom and total <= room_on_new_page):
      self.new_page()
    self.canvas.setStrokeColor(LINE); self.canvas.setLineWidth(0.5)
    self.canvas.line(MARGIN, self.y + 6, WIDTH - MARGIN, self.y + 6)
    story = list(paragraphs)
    while story:
      frame = Frame(MARGIN, bottom, width, self.y - bottom, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
      frame.addFromList(story, self.canvas)
      if story:
        self.new_page()

  def finish(self) -> bytes:
    self.canvas.save()
    return self.buffer.getvalue()


# --- the sheet ---------------------------------------------------------------------------------------------


def _day(value, what: str) -> date:
  try:
    return date.fromisoformat(str(value or ""))
  except ValueError as error:
    raise SheetProblem(f"Choose the {what} date.") from error


def make(details: dict, owner_uid: int | None = None) -> dict:
  """The sheet as {pdf (base64), file_name, dates, title}. details: group_id, start, end (YYYY-MM-DD), filled
  (true for names), notes ({html} or {text}), save_notes (true keeps the notes for this report and group next
  time; an empty note then clears them), and optionally title (else the group's Description, else its name).
  owner_uid: only that leader's groups (else any)."""
  try:
    group_id = int(details.get("group_id"))
  except (TypeError, ValueError) as error:
    raise SheetProblem("Choose a group.") from error
  start, end = _day(details.get("start"), "first"), _day(details.get("end"), "last")
  if end < start:
    raise SheetProblem("The last date comes before the first.")
  if (end - start).days >= MAX_DAYS:
    raise SheetProblem("Choose a period of a year at most.")
  filled = details.get("filled", True) is not False
  try:
    notes = clean(details.get("notes"), "notes", required=False)
  except FormattedTextProblem as problem:
    raise SheetProblem(str(problem)) from problem
  if len(notes["html"]) > NOTES_LIMIT:
    raise SheetProblem("The notes are too long for the sheet.")
  with connect() as connection:
    group = _group(connection, group_id, owner_uid)
    try:
      title = one_line(details.get("title") or group["title"], "title", TITLE_LIMIT)
    except FormattedTextProblem as problem:
      raise SheetProblem(str(problem)) from problem
    tasks = _tasks(connection, group_id)
    if not tasks:
      raise SheetProblem(f"No tasks belong to the group “{group['name']}” yet. Choose the group on each task’s Edit page (Tasks).")
    people = _people(connection, [task["id"] for task in tasks], start, end) if filled else None
    if details.get("save_notes") is True:
      connection.execute(
        """INSERT INTO report_notes (report, group_id, notes_html) VALUES (%s, %s, %s)
        ON CONFLICT (report, group_id) DO UPDATE SET notes_html = EXCLUDED.notes_html, updated_at = now()""",
        (REPORT, group_id, notes["html"]),
      )
  dates = sheet_dates(tasks, start, end, people)
  if not dates:
    raise SheetProblem("None of the group's tasks fall in that period.")
  sheet = _Sheet(title)
  for day, rows in dates:
    sheet.block(day, rows, not filled)
  sheet.notes(notes_paragraphs(notes["html"]))
  pdf = sheet.finish()
  safe = re.sub(r"[^A-Za-z0-9 .,'()-]+", "", title).strip() or "Sign-up sheet"
  if len(safe) > 80:
    safe = safe[:80].rsplit(" ", 1)[0].rstrip(" -,")
  file_name = f"{safe} {start.isoformat()} to {end.isoformat()}{'' if filled else ' (blank)'}.pdf"
  return {"pdf": base64.b64encode(pdf).decode(), "file_name": file_name, "dates": len(dates), "title": title}
