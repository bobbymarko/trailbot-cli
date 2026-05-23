"""Trailbot CLI entry points."""

import argparse
import sys
from datetime import datetime, timezone

from . import __version__
from .client import (
    find_trail,
    get_trail_status,
    open_trails,
    search_trails,
    sync_trails,
    trails_near,
)

STATUS_EMOJI = {
    "Open": "🟢",
    "Closed": "🔴",
    "Caution": "🟡",
}


def _fmt_status(status: str) -> str:
    return f"{STATUS_EMOJI.get(status, '⚪')} {status}"


def _fmt_updated(ms: int) -> str:
    try:
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone()
        return dt.strftime("%b %d %I:%M %p %Z")
    except Exception:
        return "unknown"


def cmd_status(args):
    trail_dir = find_trail(args.trail)
    if not trail_dir:
        print(f"Trail '{args.trail}' not found. Try: trailbot search <query>")
        sys.exit(1)

    org_slug = trail_dir["organization"]["slug"]
    trail_slug = trail_dir["slug"]
    t = get_trail_status(org_slug, trail_slug)

    print(f"\n{t.get('trailName', trail_slug)} — {t.get('city')}, {t.get('state')}")
    print(f"Status:  {_fmt_status(t.get('trailStatus', 'Unknown'))}")
    if t.get("statusTags"):
        print(f"Tags:    {', '.join(t['statusTags'])}")
    if t.get("updatedAt"):
        print(f"Updated: {_fmt_updated(t['updatedAt'])}")
    desc = (t.get("description") or "").strip()
    if desc:
        print(f"\n{desc}")
    print()


def cmd_search(args):
    results = search_trails(args.query, state=args.state)
    if not results:
        print("No trails found.")
        return
    for t in results[:20]:
        org = t.get("organization", {}).get("shortName", "")
        print(f"  {t['trailName']} ({t.get('city')}, {t.get('state')})  [{org}]  slug: {t['slug']}")


def cmd_near(args):
    try:
        lat, lon = map(float, args.location.split(","))
    except ValueError:
        print("Location must be 'lat,lon' e.g. 44.85,-93.52")
        sys.exit(1)

    if not args.no_sync:
        print("Fetching trail data...", end=" ", flush=True)

    results = trails_near(lat, lon, radius_miles=args.radius, state=args.state,
                          auto_sync=not args.no_sync)

    if not args.no_sync:
        print("done.")

    if not results:
        print(f"No trails within {args.radius} miles.")
        return

    open_only = not args.all
    shown = 0
    for t in results:
        status = t.get("trailStatus", "")
        if open_only and status != "Open":
            continue
        org = t.get("organization", {}).get("shortName", "")
        dist = t["_dist_miles"]
        print(f"  {_fmt_status(status)}  {t['trailName']} ({t.get('city')}, {t.get('state')})  {dist} mi  [{org}]")
        shown += 1

    if shown == 0:
        status_note = "open " if open_only else ""
        print(f"No {status_note}trails within {args.radius} miles. Try --all or a larger --radius")


def cmd_open(args):
    trails = open_trails(state=args.state)
    if not trails:
        label = f" in {args.state}" if args.state else ""
        print(f"No open trails found{label}.")
        return
    for t in trails:
        org = t.get("organization", {}).get("shortName", "")
        print(f"  🟢 {t['trailName']} ({t.get('city')}, {t.get('state')})  [{org}]")


def cmd_sync(args):
    def progress(done, total):
        print(f"\r  Fetching org data... {done}/{total}", end="", flush=True)

    print("Syncing trail data from trailbot.com...")
    trails = sync_trails(progress_cb=progress)
    print(f"\r  Done — {len(trails)} trails cached.          ")


def main():
    parser = argparse.ArgumentParser(
        prog="trailbot",
        description="Unofficial CLI for trailbot.com mountain bike trail conditions",
    )
    parser.add_argument("--version", action="version", version=f"trailbot {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = sub.add_parser("status", help="Get current status for a trail system")
    p_status.add_argument("trail", help="Trail slug or name (e.g. detroit-mountain)")
    p_status.set_defaults(func=cmd_status)

    # search
    p_search = sub.add_parser("search", help="Search trail systems by name, city, or org")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--state", help="Filter by state code (e.g. MN)")
    p_search.set_defaults(func=cmd_search)

    # near
    p_near = sub.add_parser("near", help="Find trails near a location")
    p_near.add_argument("location", help="Latitude,longitude e.g. 44.85,-93.52")
    p_near.add_argument("--radius", type=float, default=75, help="Search radius in miles (default: 75)")
    p_near.add_argument("--state", help="Filter by state code")
    p_near.add_argument("--all", action="store_true", help="Show all statuses, not just open")
    p_near.add_argument("--no-sync", action="store_true", help="Use cached data only, skip auto-sync")
    p_near.set_defaults(func=cmd_near)

    # open
    p_open = sub.add_parser("open", help="List all currently open trail systems")
    p_open.add_argument("--state", help="Filter by state code (e.g. MN)")
    p_open.set_defaults(func=cmd_open)

    # sync
    p_sync = sub.add_parser("sync", help="Fetch and cache all trail data (status + location)")
    p_sync.set_defaults(func=cmd_sync)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
