"""Emit fresh company-fenced party snapshots after Notification revision 0026."""

import argparse
import asyncio
import sys

from accounting.config import Settings
from accounting.tasks.party_contact_notifications import run_backfill


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    settings = Settings(_env_file=args.env_file)  # type: ignore[call-arg]
    sys.stdout.write(f"{asyncio.run(run_backfill(settings.database_url))}\n")


if __name__ == "__main__":
    main()
