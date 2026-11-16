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
  return os.environ.get("SITE_URL", "https://bible-and-beyond.com").rstrip("/") + path


def make_card(text: str, caption: str = "", chooser=None) -> MessageCard | None:
  """Draws a card over a picture chosen at random and saves it. None when there is no picture in use or the
  drawing fails (logged; the message then goes without a picture)."""
  try:
    chosen = verse_images.random_image(chooser) if chooser else verse_images.random_image()
    if chosen is None:
      return None
    _, background = chosen
    card = render(background, text, caption)
    folder = cards_folder()
    folder.mkdir(parents=True, exist_ok=True)
    remove_old_cards()
    name = secrets.token_urlsafe(24) + ".jpg"
    temporary = folder / f".{name}.new"
    card.save(temporary, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    os.chmod(temporary, 0o644)
    os.replace(temporary, folder / name)
    return MessageCard(folder / name, site_address(f"/api/message-card/{name}"), f"card-{name[:16]}@bible-and-beyond")
  except Exception as problem:
    logger.error("Message card not made: %s", type(problem).__name__)
    return None


# --- the email ----------------------------------------------------------------------------------------------


def attach_to_email(email, card: MessageCard, alternative_text: str) -> None:
  """Makes a plain-text email (set_content already called) show the card above its text: an HTML part with the
  picture inline (cid:) and the same text, the plain part kept for mail programs that want it."""
  from html import escape

  plain = email.get_content()
  email.add_alternative(
    f"""<!doctype html><html><body style="margin:0;padding:16px;font-family:Georgia,serif;">
<p><img src="cid:{card.content_id}" alt="{escape(alternative_text)}" width="540" style="max-width:100%;height:auto;border-radius:8px;"></p>
<div style="white-space:pre-wrap;font-size:16px;line-height:1.5;">{escape(plain)}</div>
</body></html>""",
    subtype="html",
  )
  html_part = email.get_payload()[-1]
  html_part.add_related(card.path.read_bytes(), "image", "jpeg", cid=f"<{card.content_id}>", filename="verse.jpg")


# --- what goes on the card ---------------------------------------------------------------------------------

REFERENCE_LINE = re.compile(r"^[1-3]?\s?[A-Z][A-Za-z. ]+\s\d+:\d+(?:[-–,]\s?\d+)*\.?$")
TRAILING_REFERENCE = re.compile(r"^(.*\S)\s*—\s*((?:[1-3]\s?)?[A-Za-z]+\.?\s\d+:\d+(?:\s?[-–,]\s?\d+)*)\.?$", re.DOTALL)


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
    book = " ".join(word.capitalize() if word.isalpha() or word.rstrip(".").isalpha() else word for word in joined.group(2).split(" "))
    return joined.group(1), book
  first = paragraphs[0] if paragraphs else reading["title"]
  if len(first) > 400:
    first = first[:400].rsplit(" ", 1)[0] + "…"
  return first, reading["title"]
