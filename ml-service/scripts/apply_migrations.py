"""Apply every file in database/migrations, in order. Each is written to be safe to run again.

Run (from ml-service):

    .venv/bin/python scripts/apply_migrations.py

The containers run it on every start (docker/web/entrypoint.sh), as deploy/deploy.sh does with psql on the
server, so a newer image brings an existing database up to date.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from search import connect  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parent.parent / "database" / "migrations"


def main():
  files = sorted(MIGRATIONS.glob("*.sql"))
  with connect() as connection:
    for path in files:
      # No parameters, so the whole file (several statements) is sent at once.
      connection.execute(path.read_text(encoding="utf-8"))
      connection.commit()
  print(f"Applied {len(files)} migrations.")


if __name__ == "__main__":
  main()
