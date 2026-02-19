#!/usr/bin/env python3
"""CLI for MTGTop8 scraper and metagame analyzer."""

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="MTGTop8 scraper and metagame analyzer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape_parser = subparsers.add_parser("scrape", help="Scrape deck lists")
    scrape_parser.add_argument("--format", "-f", default="EDH", help="Format ID (default: EDH)")
    scrape_parser.add_argument("--period", "-p", help="Time period (e.g. 'Last 2 Weeks')")
    scrape_parser.add_argument("--meta", "-m", type=int, help="Override meta value")
    scrape_parser.add_argument("--store", "-s", help="Filter events by store/location substring")
    scrape_parser.add_argument(
        "--events", "-e",
        help="Comma-separated event IDs (skip format page)",
    )
    scrape_parser.add_argument("-o", "--output", required=True, help="Output JSON file")

    analyze_parser = subparsers.add_parser("analyze", help="Analyze scraped decks")
    analyze_parser.add_argument("input", help="Input JSON file (decks)")
    analyze_parser.add_argument("-o", "--output", required=True, help="Output JSON file")
    analyze_parser.add_argument(
        "--placement-weighted",
        action="store_true",
        help="Weight stats by placement (1 > 2 > 3-4 > ...)",
    )

    args = parser.parse_args()

    if args.command == "scrape":
        from src.mtgtop8.scraper import scrape

        event_ids = None
        if args.events:
            event_ids = [int(x.strip()) for x in args.events.split(",")]

        def on_progress(msg: str) -> None:
            print(msg, file=sys.stderr)

        decks = scrape(
            format_id=args.format,
            period=args.period,
            meta=args.meta,
            store=args.store,
            event_ids=event_ids,
            on_progress=on_progress,
        )
        data = [d.to_dict() for d in decks]
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(decks)} decks to {args.output}", file=sys.stderr)
        return 0

    if args.command == "analyze":
        from src.mtgtop8.analyzer import analyze, write_report
        from src.mtgtop8.models import Deck

        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
        decks = [Deck.from_dict(d) for d in data]
        report = analyze(decks, placement_weighted=args.placement_weighted)
        write_report(report, args.output)
        print(f"Saved metagame report to {args.output}", file=sys.stderr)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
