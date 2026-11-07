"""Download the STEPBible data the Original Words and lexicon windows use, from STEPBible's own repository.

Run (from ml-service):

    .venv/bin/python scripts/download_stepbible.py data/stepbible

It saves the four TAHOT files and the two TAGNT files ("Translators Amalgamated OT+NT") and the TBESH and
TBESG lexicons ("Lexicons") from https://github.com/STEPBible/STEPBible-Data (CC BY 4.0, by STEP Bible and
Tyndale House, Cambridge; about 110 MB) in that folder. Then load them with
scripts/import_original_words.py. STEPBible asks that copies of these files not be posted elsewhere, so
each site downloads them from STEPBible itself (the containers do it on their first start).
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

import httpx

REPOSITORY = "STEPBible/STEPBible-Data"
FOLDERS = {
  "Translators Amalgamated OT+NT": ("TAHOT", "TAGNT"),
  "Lexicons": ("TBESH", "TBESG"),
}
EXPECTED_FILES = 8
HEADERS = {"User-Agent": "bible-and-beyond (https://github.com/PaulCarrick/bible-and-beyond.com)"}


def list_files(client: httpx.Client) -> list[tuple[str, str]]:
  """The (name, download address) of each file to fetch, from the repository's current contents."""
  files = []
  for folder, prefixes in FOLDERS.items():
    response = client.get(f"https://api.github.com/repos/{REPOSITORY}/contents/{quote(folder)}")
    response.raise_for_status()
    for entry in response.json():
      if entry["type"] == "file" and entry["name"].upper().startswith(prefixes) and entry["name"].endswith(".txt"):
        files.append((entry["name"], entry["download_url"]))
  return files


def download(folder: Path) -> int:
  folder.mkdir(parents=True, exist_ok=True)
  with httpx.Client(headers=HEADERS, timeout=120, follow_redirects=True) as client:
    files = list_files(client)
    if len(files) != EXPECTED_FILES:
      raise RuntimeError(f"Expected {EXPECTED_FILES} STEPBible files, found {len(files)}: {[name for name, _ in files]}")
    for name, address in files:
      target = folder / name
      partial = target.with_name(target.name + ".part")
      with client.stream("GET", address) as response:
        response.raise_for_status()
        with open(partial, "wb") as file:
          for chunk in response.iter_bytes():
            file.write(chunk)
      partial.replace(target)
      print(f"  {name} ({target.stat().st_size:,} bytes)")
  return len(files)


def main():
  parser = argparse.ArgumentParser(description="Download the STEPBible original-language data and lexicons.")
  parser.add_argument("folder", help="Folder to save the files in")
  arguments = parser.parse_args()
  try:
    count = download(Path(arguments.folder))
  except (httpx.HTTPError, RuntimeError, OSError) as problem:
    print(f"Download failed: {problem}", file=sys.stderr)
    sys.exit(1)
  print(f"Downloaded {count} files to {arguments.folder}.")


if __name__ == "__main__":
  main()
