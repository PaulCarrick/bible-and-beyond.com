"""Picture messages ("Send Multimedia Messages", added 2026-11-16 at the owner's request).

A member who ticks Send Multimedia Messages gets the verse a day and the daily devotional as a picture: the
words written over one of the verse a day pictures (verse_images.py), chosen at random, in a large script font
(Dancing Script, SIL Open Font License, fonts/) in white with a dark outline and a soft shadow, so they can be
read over any picture. The picture goes inline in the email, and as an MMS with the text message.

A card is a 1080 × 1350 JPEG (portrait, as phones show pictures; well under the 1 MB carriers allow for MMS).
Telnyx fetches an MMS picture from a public address, so each card is saved in the message cards folder
(MESSAGE_CARDS_FOLDER, ml-service/data/message-cards until set) under a random name and served at
/message-card/<name>.jpg; it holds only the verse or reading, never anything about the member, and cards older
than KEEP_DAYS are deleted whenever a new one is made. With no picture in use, or if drawing fails, make_card
gives None and the message goes as before, without a picture.
"""

import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from site_settings import get_public_settings
import verse_images

logger = logging.getLogger("message_cards")

WIDTH, HEIGHT = 1080, 1350
MARGIN = 90
FONT_PATH = Path(__file__).resolve().parent / "fonts" / "DancingScript.ttf"
# The words start large and shrink until they fit; below the smallest they are cut with "…".
LARGEST_SIZE, SMALLEST_SIZE = 112, 48
LINE_SPACING = 1.22
JPEG_QUALITY = 86
KEEP_DAYS = 7
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,64}\.jpg$")


@dataclass
class MessageCard:
  path: Path
  url: str
  # The Content-ID the email's HTML uses for it.
  content_id: str


def cards_folder() -> Path:
  return Path(os.environ.get("MESSAGE_CARDS_FOLDER") or Path(__file__).resolve().parent / "data" / "message-cards")


def card_file(name: str) -> Path | None:
  """The saved card with that name, or None (a bad name is never looked up)."""
  if not NAME_PATTERN.match(name or ""):
    return None
  path = cards_folder() / name
  return path if path.is_file() else None


def _font(size: int, bold: bool = True):
  from PIL import ImageFont

  font = ImageFont.truetype(str(FONT_PATH), size)
  try:
    font.set_variation_by_axes([700 if bold else 500])
  except (OSError, AttributeError):  # a FreeType without variable fonts: the font's own weight
    pass
  return font


def _wrap(words: list[str], font, width: int) -> list[str]:
  lines, line = [], ""
  for word in words:
    trial = f"{line} {word}".strip()
    if line and font.getlength(trial) > width:
      lines.append(line)
      line = word
    else:
      line = trial
  if line:
    lines.append(line)
  return lines


def fit_text(text: str, width: int, height: int) -> tuple[int, list[str]]:
  """The largest size (and its lines) at which the words fit the box; at the smallest size, as many words as fit
  followed by "…"."""
  words = text.split()
  for size in range(LARGEST_SIZE, SMALLEST_SIZE - 1, -4):
    font = _font(size)
    lines = _wrap(words, font, width)
    if len(lines) * size * LINE_SPACING <= height and all(font.getlength(line) <= width for line in lines):
      return size, lines
  font = _font(SMALLEST_SIZE)
  room = max(1, int(height // (SMALLEST_SIZE * LINE_SPACING)))
  # The most words that fit with "…" after them (a binary search: a long reading has thousands of words).
  fits = lambda count: len(_wrap(words[:count] + ["…"], font, width)) <= room
  low, high = 0, len(words)
  while low < high:
    middle = (low + high + 1) // 2
    if fits(middle):
      low = middle
    else:
      high = middle - 1
  return SMALLEST_SIZE, _wrap(words[:low] + ["…"], font, width)


def _cover(picture, width: int, height: int):
  """The picture scaled to cover the card and cut to it, around its middle."""
  from PIL import Image, ImageOps

  picture = ImageOps.exif_transpose(picture).convert("RGB")
  return ImageOps.fit(picture, (width, height), Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _draw_lines(card, lines: list[tuple[str, object, int]], top: int) -> int:
  """Draws centred lines (text, font, line height) from top, white with a dark outline over a soft shadow.
  Returns where the last line ended."""
  from PIL import Image, ImageDraw, ImageFilter

  shadow = Image.new("L", card.size, 0)
  shadow_draw = ImageDraw.Draw(shadow)
  y = top
  placed = []
  for text, font, line_height in lines:
    x = (WIDTH - font.getlength(text)) / 2
    placed.append((x, y, text, font))
    stroke = max(2, round(font.size / 16))
    shadow_draw.text((x + 4, y + 6), text, font=font, fill=255, stroke_width=stroke * 2)
    y += line_height
  # The shadow: a blurred dark copy of the words under them, so they stand out from a light picture.
  shadow = shadow.filter(ImageFilter.GaussianBlur(10))
  card.paste((0, 0, 0), (0, 0), shadow.point(lambda value: int(value * 0.75)))
  draw = ImageDraw.Draw(card)
  for x, y_line, text, font in placed:
    stroke = max(2, round(font.size / 16))
    draw.text((x, y_line), text, font=font, fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(20, 20, 30))
  return y


def plain_background():
  """A deep blue background, lighter at the top, for when no verse a day picture is in use."""
  from PIL import Image

  top, bottom = (54, 84, 140), (14, 24, 52)
  column = Image.new("RGB", (1, HEIGHT))
  for y in range(HEIGHT):
    share = y / (HEIGHT - 1)
    column.putpixel((0, y), tuple(round(a + (b - a) * share) for a, b in zip(top, bottom)))
  return column.resize((WIDTH, HEIGHT))


def render(background, text: str, caption: str = ""):
  """The card as a Pillow picture: the background (a file's path, or a Pillow picture) covering it, darkened a
  little, the words as large as fit, the caption (a reference) under them, and the site's name at the foot."""
  from PIL import Image

  if isinstance(background, Image.Image):
    card = _cover(background, WIDTH, HEIGHT)
  else:
    with Image.open(background) as picture:
      picture.load()
      card = _cover(picture, WIDTH, HEIGHT)
  # A gentle dark veil over the whole picture, so white words read on light pictures too.
  card = Image.blend(card, Image.new("RGB", card.size, (0, 0, 0)), 0.28)

  caption_font = _font(64)
  footer_font = _font(40, bold=False)
  caption_height = round(64 * 1.6) if caption else 0
  room = HEIGHT - 2 * MARGIN - caption_height - 80
  size, lines = fit_text(" ".join(text.split()), WIDTH - 2 * MARGIN, room)
  font = _font(size)
  line_height = round(size * LINE_SPACING)
  block = len(lines) * line_height + caption_height
  top = max(MARGIN, (HEIGHT - 80 - block) // 2)
  drawn = [(line, font, line_height) for line in lines]
  if caption:
    drawn.append(("", caption_font, round(64 * 0.6)))
    drawn.append((caption, caption_font, 64))
  _draw_lines(card, drawn, top)
  _draw_lines(card, [(get_public_settings()["title"], footer_font, 40)], HEIGHT - MARGIN + 10 - 40)
  return card


def card_from_name(name: str) -> MessageCard | None:
  """A card saved earlier (a group's preview), to send; None when it is gone (older than KEEP_DAYS) or the name
  is not one of ours."""
  path = card_file(name)
  if path is None:
    return None
  return MessageCard(path, site_address(f"/api/message-card/{name}"), f"card-{name[:16]}@bible-and-beyond")


def data_address(card: MessageCard) -> str:
  """The card as a data: address, to show it in a page."""
  import base64

  return "data:image/jpeg;base64," + base64.b64encode(card.path.read_bytes()).decode()


def remove_old_cards(now: float | None = None) -> int:
  """Deletes cards older than KEEP_DAYS. Returns how many."""
  limit = (now or time.time()) - KEEP_DAYS * 24 * 60 * 60
  removed = 0
  for path in cards_folder().glob("*.jpg"):
    try:
      if path.stat().st_mtime < limit:
        path.unlink()
        removed += 1
    except OSError:
      pass
  return removed


def site_address(path: str) -> str:
  return os.environ.get("SITE_URL", "https://freestudy.bible").rstrip("/") + path


def created_by() -> str:
  """The line that ends every verse we send, the verse a day and the cards members make (the owner's request,
  2026-11-26): "Created by Free Study Bible (https://freestudy.bible)". In the HTML version the address is a link
  (paragraphs_html)."""
  return f"Created by {get_public_settings()['title']} ({site_address('')})"


def make_card(text: str, caption: str = "", chooser=None, plain_if_none: bool = False) -> MessageCard | None:
  """Draws a card over a picture chosen at random and saves it. None when there is no picture in use (unless
  plain_if_none: then on the plain deep-blue background) or the drawing fails (logged; the message then goes
  without a picture)."""
  try:
    chosen = verse_images.random_image(chooser) if chooser else verse_images.random_image()
    if chosen is None and not plain_if_none:
      return None
    background = chosen[1] if chosen else plain_background()
    return save_card(render(background, text, caption))
  except Exception as problem:
    logger.error("Message card not made: %s", type(problem).__name__)
    return None


def save_card(card) -> MessageCard:
  """Saves a drawn card (a Pillow picture) under a random name, so an email can carry it and a text (MMS) can
  fetch it from its public address. Cards are deleted after KEEP_DAYS."""
  folder = cards_folder()
  folder.mkdir(parents=True, exist_ok=True)
  remove_old_cards()
  name = secrets.token_urlsafe(24) + ".jpg"
  temporary = folder / f".{name}.new"
  card.save(temporary, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
  os.chmod(temporary, 0o644)
  os.replace(temporary, folder / name)
  return MessageCard(folder / name, site_address(f"/api/message-card/{name}"), f"card-{name[:16]}@bible-and-beyond")


# --- the email ----------------------------------------------------------------------------------------------


WEB_ADDRESS = re.compile(r"https?://[^\s<>\"]+")


def _linked(text: str) -> str:
  """Plain text as HTML, with every web address in it a link."""
  from html import escape

  parts, start = [], 0
  for found in WEB_ADDRESS.finditer(text):
    address = found.group(0).rstrip(".,)")
    parts += [escape(text[start:found.start()]), f'<a href="{escape(address)}">{escape(address)}</a>']
    start = found.start() + len(address)
  return "".join(parts + [escape(text[start:])])


PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
TEXT_STYLE = "margin:0 0 14px;font-size:16px;line-height:1.55;"


def paragraphs_html(text: str) -> str:
  """Plain text as paragraphs of HTML (the owner's request, 2026-11-17: the text under the picture was one block
  with no breaks in some mail programs, which ignore white-space). A blank line starts a paragraph and a single line
  break is kept; a short line in capitals (MORNING, EVENING) becomes a heading; the "--" signature and what follows it
  are smaller and grey. Web addresses are links."""
  html_parts = []
  in_footer = False
  for block in PARAGRAPH_BREAK.split(text.strip()):
    lines = [line.rstrip() for line in block.strip("\n").split("\n")]
    if not any(line.strip() for line in lines):
      continue
    if lines[0].strip() == "--":
      in_footer = True
      lines = lines[1:]
      if not lines:
        continue
    joined = "<br>".join(_linked(line) for line in lines)
    plain = " ".join(line.strip() for line in lines)
    if in_footer:
      html_parts.append(f'<p style="margin:0 0 6px;font-size:13px;line-height:1.5;color:#666;">{joined}</p>')
    elif len(lines) == 1 and len(plain) <= 40 and plain.upper() == plain and any(character.isalpha() for character in plain):
      html_parts.append(f'<h3 style="margin:22px 0 8px;font-size:15px;letter-spacing:0.08em;">{joined}</h3>')
    else:
      html_parts.append(f'<p style="{TEXT_STYLE}">{joined}</p>')
  if in_footer:
    # A line between the message and the signature.
    first_footer = next((index for index, part in enumerate(html_parts) if "color:#666" in part), None)
    if first_footer is not None:
      html_parts.insert(first_footer, '<hr style="border:0;border-top:1px solid #ddd;margin:24px 0 12px;">')
  return "\n".join(html_parts)


def attach_to_email(email, card: MessageCard | None, alternative_text: str = "", link: str | None = None, linked_lines: int = 0) -> None:
  """Adds an HTML version to a plain-text email (set_content already called), the plain part kept for mail
  programs that want it. With a card, the picture comes first (inline, cid:). With a link, the picture and the
  first linked_lines lines of the text (the verse and its reference) are links to it (the owner's request,
  2026-11-16: the verse a link to the verse on the site). Every web address in the rest is a link too."""
  from html import escape

  lines = email.get_content().split("\n")
  lead, rest = lines[:linked_lines], "\n".join(lines[linked_lines:])
  picture = ""
  if card is not None:
    picture = (
      f'<img src="cid:{card.content_id}" alt="{escape(alternative_text)}" width="540" '
      'style="max-width:100%;height:auto;border-radius:8px;border:0;">'
    )
    if link:
      picture = f'<a href="{escape(link)}">{picture}</a>'
    picture = f"<p>{picture}</p>"
  lead_html = "".join(
    f'<p style="margin:0 0 4px;font-size:18px;"><a href="{escape(link)}" style="color:#1d3f8a;">{escape(line)}</a></p>'
    for line in lead
    if line.strip() and link
  )
  email.add_alternative(
    f"""<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0;padding:16px;font-family:Georgia,serif;">
{picture}{lead_html}<div style="max-width:640px;">{paragraphs_html(rest)}</div>
</body></html>""",
    subtype="html",
  )
  if card is not None:
    html_part = email.get_payload()[-1]
    html_part.add_related(card.path.read_bytes(), "image", "jpeg", cid=f"<{card.content_id}>", filename="verse.jpg")


def attach_card_file(email, card: MessageCard, alternative_text: str = "") -> None:
  """A member's saved verse card attached to a group message (saved_cards.py; 2026-11-26): shown in the email's
  HTML (cid:, above the words; an HTML version is made when the message had none) and attached as a JPEG they can
  save."""
  import re
  from html import escape

  if not email.is_multipart():
    attach_to_email(email, card, alternative_text)
  else:
    html_part = email.get_body(preferencelist=("html",))
    picture = (
      f'<p><img src="cid:{card.content_id}" alt="{escape(alternative_text[:300])}" width="540" '
      'style="max-width:100%;height:auto;border-radius:8px;border:0;"></p>'
    )
    content, found = re.subn(r"(<body[^>]*>)", lambda match: match.group(1) + picture, html_part.get_content(), count=1)
    html_part.set_content(content if found else picture + content, subtype="html")
    html_part.add_related(card.path.read_bytes(), "image", "jpeg", cid=f"<{card.content_id}>", filename="verse.jpg")
  email.add_attachment(card.path.read_bytes(), maintype="image", subtype="jpeg", filename="verse-card.jpg")


# --- what goes on the card ---------------------------------------------------------------------------------

REFERENCE_LINE = re.compile(r"^[1-3]?\s?[A-Z][A-Za-z. ]+\s\d+:\d+(?:[-–,]\s?\d+)*\.?$")
# A verse with its reference at the end of the same paragraph, as the daily devotionals write it:
#   Daily Light                    Fellow citizens with the saints.—EPH. 2:19.
#   Daily Strength for Daily Needs  Love is of God ... knoweth God — I John 4:7
#   Faith's Checkbook               "No weapon ... shalt condemn" Isa. 54:17
#   Streams in the Desert           “Be ready in the morning ... with thee.” (Exod. 34:2, 3.)
TRAILING_REFERENCE = re.compile(
  r"^(.*?\S)\s*(?:—\s*|\s)\(?((?:(?:[1-3]|I{1,3})\s?)?[A-Za-z]+\.?\s\d+:\d+(?:\s?[-–,]\s?\d+)*)\.?\)?\.?$",
  re.DOTALL,
)


def devotional_words(reading: dict, entry_index: int = 0) -> tuple[str, str]:
  """The words and caption for a devotional reading's card: its opening verse and reference when it starts with
  one (Morning and Evening, Daily Light), else its opening paragraph and the reading's title. entry_index picks
  the evening reading of a day that has two."""
  entry = reading["entries"][entry_index]
  paragraphs = [paragraph.strip() for paragraph in entry["text"].split("\n\n") if paragraph.strip()]
  if len(paragraphs) >= 2 and REFERENCE_LINE.match(paragraphs[1]):
    return paragraphs[0], paragraphs[1].rstrip(".")
  # Daily Light: "Fellow citizens with the saints.—EPH. 2:19." on one line.
  joined = TRAILING_REFERENCE.match(paragraphs[0]) if paragraphs else None
  if joined:
    # "EPH. 2:19" as "Eph. 2:19"; "I John 4:7" stays.
    reference = " ".join(
      word.capitalize() if len(word.rstrip(".")) > 1 and word.rstrip(".").isalpha() and word.isupper() else word
      for word in joined.group(2).split(" ")
    )
    return joined.group(1), reference
  first = paragraphs[0] if paragraphs else reading["title"]
  if len(first) > 400:
    first = first[:400].rsplit(" ", 1)[0] + "…"
  return first, reading["title"]
