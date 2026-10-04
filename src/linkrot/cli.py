from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .check import Checker, Options, find_docs


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="linkrot",
        description="Find dead links in Markdown and HTML files.",
    )
    p.add_argument("paths", nargs="*", type=Path, default=[Path(".")], help="files or directories (default: .)")
    p.add_argument("--offline", action="store_true", help="only check links between local files")
    p.add_argument("--ignore", action="append", default=[], metavar="PATTERN",
                   help="skip links matching this glob, e.g. 'https://localhost*' (repeatable)")
    p.add_argument("--timeout", type=float, default=10.0, help="seconds per request (default: 10)")
    p.add_argument("--workers", type=int, default=16, help="parallel requests (default: 16)")
    p.add_argument("--strict", action="store_true",
                   help="also fail on 401/403/429, which usually mean bot protection rather than a dead page")
    p.add_argument("--json", action="store_true", help="print problems as JSON")
    p.add_argument("--version", action="version", version=f"linkrot {__version__}")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    missing = [str(p) for p in args.paths if not p.exists()]
    if missing:
        print(f"linkrot: no such file or directory: {', '.join(missing)}", file=sys.stderr)
        return 2

    docs = find_docs(args.paths)
    opts = Options(
        external=not args.offline,
        timeout=args.timeout,
        workers=max(1, args.workers),
        ignore=tuple(args.ignore),
    )
    started = time.monotonic()
    problems, total = Checker(opts).run(docs)

    if args.json:
        json.dump(
            [
                {"file": str(p.file), "line": p.line, "link": p.target, "reason": p.reason, "warning": p.warning}
                for p in problems
            ],
            sys.stdout,
            indent=2,
        )
        print()
    else:
        for p in problems:
            note = ", may be bot protection" if p.warning else ""
            print(f"{p.file}:{p.line}: {p.target} ({p.reason}{note})")
        elapsed = time.monotonic() - started
        files = f"{len(docs)} file{'s' * (len(docs) != 1)}"
        broken = sum(not p.warning for p in problems)
        unsure = len(problems) - broken
        parts = [f"{total} links in {files}", f"{broken} broken" if broken else "none broken"]
        if unsure:
            parts.append(f"{unsure} unsure")
        print(f"{', '.join(parts)} ({elapsed:.1f}s)", file=sys.stderr)

    failing = [p for p in problems if args.strict or not p.warning]
    return 1 if failing else 0
