"""Command-line entry point: `accountscope scan` and `accountscope change`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from accountscope import __version__
from accountscope.change import KINDS, build_checklist, render_markdown, render_terminal
from accountscope.classify import classify, load_rules
from accountscope.facts import extract_facts, merge_facts
from accountscope.identity import SelfDetector
from accountscope.inventory import Aggregator
from accountscope.mbox import BodyReader, MboxStats, NotAnMbox, check_mbox, iter_messages
from accountscope.orgs import identify, load_relays
from accountscope.report import render_summary, write_csv, write_json
from accountscope.viewer import write_html


def _err(message: str) -> None:
    print(f"accountscope: {message}", file=sys.stderr)


def run_scan(args: argparse.Namespace) -> int:
    path = Path(args.mbox)
    if not path.exists():
        _err(f"{path} does not exist")
        return 2
    try:
        check_mbox(path)
    except NotAnMbox as exc:
        _err(str(exc))
        return 2

    rules = load_rules()
    relays = load_relays()
    stats = MboxStats()
    detector = SelfDetector()
    aggregator = Aggregator()
    first_day = last_day = None

    for message in iter_messages(path, stats):
        detector.add(message.recipients)
        identity = identify(message.sender, message.sender_name, message.reply_to, relays)
        msg_type = classify(message.subject, message.has_list_unsubscribe, rules)
        aggregator.add(message, identity, msg_type)
        if message.date:
            day = message.date.date().isoformat()
            first_day = day if first_day is None else min(first_day, day)
            last_day = day if last_day is None else max(last_day, day)

    if stats.total == 0:
        _err(f"{path} contains no messages")
        return 2
    self_addresses = detector.resolve(stats.total, args.me or [], args.not_me or [])
    if not self_addresses:
        _err("could not find any recipient address that looks like yours (this export may strip To/Delivered-To headers); "
             "pass your address with --me, e.g. --me you@example.com")
        return 2

    source = {"path": str(path), "messages": stats.total, "skipped": stats.skipped,
              "date_range": [first_day, last_day] if first_day else None}
    inventory = aggregator.finish(source, self_addresses)

    body_failures = 0
    reader = BodyReader(path)
    try:
        for org in inventory.organisations:
            hits = []
            for seen, key in org.pass2:
                text = reader.text(key)
                if not text:
                    body_failures += 1
                    continue
                hits.extend(extract_facts(text, seen or (org.last_seen or "")))
            org.holds = merge_facts(hits)
    finally:
        reader.close()

    out_dir = Path(args.out_dir) if args.out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    data = inventory.to_dict()
    outputs = []
    json_path = out_dir / "accountscope.json"
    write_json(data, json_path)
    outputs.append(json_path)
    if not args.no_html:
        html_path = out_dir / "accountscope.html"
        write_html(data, html_path)
        outputs.append(html_path)
    if args.csv:
        csv_path = out_dir / "accountscope.csv"
        write_csv(data, csv_path)
        outputs.append(csv_path)

    print(render_summary(data, {"skipped": stats.skipped, "no_recipients": stats.no_recipients,
                                "body_failures": body_failures}, outputs))
    return 0


def run_change(args: argparse.Namespace) -> int:
    inv_path = Path(args.inventory)
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _err(f"cannot read inventory {inv_path}: {exc}")
        return 2
    if not isinstance(data, dict):
        _err(f"unsupported inventory {inv_path}: expected a JSON object with a schema field")
        return 2
    schema = str(data.get("schema", ""))
    if not schema.startswith("accountscope/1"):
        _err(f"unsupported inventory schema {schema!r}; expected accountscope/1")
        return 2
    try:
        rows = build_checklist(data, args.kind, args.old, args.new)
    except ValueError as exc:
        _err(str(exc))
        return 2
    print(render_terminal(rows, args.kind, args.old, args.new))
    if args.out:
        Path(args.out).write_text(render_markdown(rows, args.kind, args.old, args.new), encoding="utf-8")
        print(f"\nwritten: {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="accountscope",
                                     description="Inventory the organisations that hold an account for you, from a mailbox export. Zero network.")
    parser.add_argument("--version", action="version", version=f"accountscope {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="build the inventory from an mbox file")
    scan.add_argument("mbox", help="path to an mbox file (Google Takeout, Thunderbird)")
    scan.add_argument("--me", action="append", metavar="ADDR", help="an address that is yours (repeatable)")
    scan.add_argument("--not-me", action="append", metavar="ADDR", help="an address to exclude (repeatable)")
    scan.add_argument("--out-dir", metavar="DIR", help="where to write outputs (default: next to the mbox)")
    scan.add_argument("--csv", action="store_true", help="also write accountscope.csv")
    scan.add_argument("--no-html", action="store_true", help="skip the HTML viewer")
    scan.set_defaults(func=run_scan)

    change = sub.add_parser("change", help="list the organisations to update after a change")
    change.add_argument("kind", choices=KINDS)
    change.add_argument("old", nargs="?", default=None, help="the old value (email address, phone, address fragment, card tail)")
    change.add_argument("new", nargs="?", default=None, help="the new value, for the checklist title")
    change.add_argument("inventory", help="path to accountscope.json")
    change.add_argument("--out", metavar="FILE", help="also write a Markdown checklist")
    change.set_defaults(func=run_change)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _err("interrupted")
        return 1
    except Exception as exc:  # noqa: BLE001 - last-resort reporting
        _err(f"unexpected error: {exc}")
        return 1
