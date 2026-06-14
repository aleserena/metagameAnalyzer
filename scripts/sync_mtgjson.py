#!/usr/bin/env python3
"""Sync card metadata (and optionally prices) from MTGJSON into the ``cards`` table.

Downloads MTGJSON bulk files and upserts the Postgres ``cards`` table that
``lookup_cards`` reads from. Metadata and prices are separate steps (prices are
larger and change daily). Requires PostgreSQL (``DATABASE_URL``).

Usage (from project root):
  python3 scripts/sync_mtgjson.py                 # metadata only (AtomicCards + AllIdentifiers)
  python3 scripts/sync_mtgjson.py --prices        # prices only (AllPricesToday)
  python3 scripts/sync_mtgjson.py --all           # metadata then prices
  python3 scripts/sync_mtgjson.py --env staging   # load .env.staging override
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync MTGJSON card data into the cards table.")
    parser.add_argument("--prices", action="store_true", help="Sync prices only (AllPricesToday).")
    parser.add_argument("--all", action="store_true", help="Sync metadata then prices.")
    parser.add_argument("--env", choices=("dev", "staging", "prod"), help="Load .env.<env> override.")
    args = parser.parse_args()

    if args.env:
        os.environ["DB_ENV"] = args.env

    # Importing api.config loads .env (and the DB_ENV override) before db reads DATABASE_URL.
    import api.config  # noqa: F401
    from api import db as _db
    from api.services import mtgjson

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not _db.is_database_available():
        print("DATABASE_URL is not set or not a PostgreSQL URL. Aborting.", file=sys.stderr)
        return 1

    do_metadata = args.all or not args.prices
    do_prices = args.all or args.prices

    if do_metadata:
        result = mtgjson.sync_metadata()
        print(f"Metadata synced: {result['cards_synced']} cards")
    if do_prices:
        result = mtgjson.sync_prices()
        print(f"Prices updated: {result['prices_updated']} cards")
    return 0


if __name__ == "__main__":
    sys.exit(main())
