from __future__ import annotations

import argparse
import webbrowser

from .ingest import ensure_data, ingest
from .server import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sfalert",
        description="Local San Francisco CAD store, live map, and heatmap.",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_ingest = sub.add_parser("ingest", help="Pull CAD into local SQLite")
    p_ingest.add_argument("--days", type=int, default=30, help="Closed-call backfill window")
    p_ingest.add_argument("--no-realtime", action="store_true")
    p_ingest.add_argument("--no-backfill", action="store_true")

    p_serve = sub.add_parser("serve", help="Open the local map UI")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--no-poll", action="store_true")

    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-poll", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.cmd == "ingest":
        ingest(
            days=args.days,
            realtime=not args.no_realtime,
            backfill=not args.no_backfill,
        )
        return

    if args.cmd == "serve":
        serve(host=args.host, port=args.port, poll=not args.no_poll)
        return

    ensure_data(days=args.days)
    if not args.no_browser:
        url = f"http://{args.host}:{args.port}"
        try:
            webbrowser.open(url)
        except Exception:
            pass
    serve(host=args.host, port=args.port, poll=not args.no_poll)


if __name__ == "__main__":
    main()
