"""Decide whether each link still resolves."""

from __future__ import annotations

import fnmatch
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .extract import Link, anchors, links

DOC_SUFFIXES = {".md", ".markdown", ".mdown", ".html", ".htm"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "target", "dist", "build"}
# Sites behind bot protection answer scripts with these even when the page is fine.
SOFT_STATUSES = {401, 403, 429}
SKIP_SCHEMES = {"mailto", "tel", "data", "javascript", "ftp", "irc"}
USER_AGENT = f"linkrot/{__version__} (+https://github.com/Shabfom/linkrot)"


@dataclass
class Problem:
    file: Path
    line: int
    target: str
    reason: str
    warning: bool = False


@dataclass
class Options:
    external: bool = True
    timeout: float = 10.0
    workers: int = 16
    ignore: tuple[str, ...] = ()
    retries: int = 1


def find_docs(paths: list[Path]) -> list[Path]:
    docs = []
    for p in paths:
        if p.is_file():
            docs.append(p)
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(files):
                if Path(name).suffix.lower() in DOC_SUFFIXES:
                    docs.append(Path(root) / name)
    return docs


def _is_html(path: Path) -> bool:
    return path.suffix.lower() in {".html", ".htm"}


class Checker:
    def __init__(self, opts: Options):
        self.opts = opts
        self._anchor_cache: dict[Path, set[str]] = {}
        self._ssl = ssl.create_default_context()

    # -- local -------------------------------------------------------------

    def _anchors_of(self, path: Path) -> set[str]:
        path = path.resolve()
        if path not in self._anchor_cache:
            text = path.read_text(encoding="utf-8", errors="replace")
            self._anchor_cache[path] = anchors(text, _is_html(path))
        return self._anchor_cache[path]

    def check_local(self, source: Path, target: str) -> str | None:
        path_part, _, fragment = target.partition("#")
        path_part = urllib.parse.unquote(path_part.split("?", 1)[0])
        if path_part.startswith("/"):
            # Site-absolute paths depend on how the docs are served; nothing to check.
            return None
        dest = (source.parent / path_part) if path_part else source
        if not dest.exists():
            return "file not found"
        if fragment and dest.is_file() and dest.suffix.lower() in DOC_SUFFIXES:
            frag = urllib.parse.unquote(fragment).lower()
            if frag not in {a.lower() for a in self._anchors_of(dest)}:
                return f"no heading #{fragment}"
        return None

    # -- remote ------------------------------------------------------------

    def _request(self, url: str, method: str) -> tuple[int, str]:
        req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.opts.timeout, context=self._ssl) as resp:
                return resp.status, ""
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers.get("Retry-After", "")

    def check_url(self, url: str) -> str | None:
        last = None
        for attempt in range(self.opts.retries + 1):
            retry_after = ""
            try:
                status, retry_after = self._request(url, "HEAD")
                # Plenty of servers reject HEAD outright; ask properly before calling it dead.
                if status >= 400:
                    status, retry_after = self._request(url, "GET")
                if status < 400:
                    return None
                last = f"HTTP {status}"
                if status < 500 and status != 429:
                    return last
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, ssl.SSLError) as e:
                reason = getattr(e, "reason", e)
                last = "timed out" if isinstance(reason, (socket.timeout, TimeoutError)) else str(reason)
            except ValueError as e:
                return str(e)
            if attempt < self.opts.retries:
                time.sleep(min(int(retry_after), 10) if retry_after.isdigit() else 1)
        return last

    # -- driver ------------------------------------------------------------

    def ignored(self, target: str) -> bool:
        return any(fnmatch.fnmatch(target, pat) for pat in self.opts.ignore)

    def run(self, docs: list[Path]) -> tuple[list[Problem], int]:
        problems: list[Problem] = []
        remote: dict[str, list[tuple[Path, Link]]] = {}
        total = 0
        for doc in docs:
            text = doc.read_text(encoding="utf-8", errors="replace")
            for link in links(text, _is_html(doc)):
                target = link.target.strip()
                if not target or self.ignored(target):
                    continue
                scheme = urllib.parse.urlsplit(target).scheme.lower()
                if scheme in SKIP_SCHEMES:
                    continue
                total += 1
                if scheme in ("http", "https"):
                    if self.opts.external:
                        remote.setdefault(target.split("#", 1)[0], []).append((doc, link))
                    continue
                if scheme:
                    continue
                reason = self.check_local(doc, target)
                if reason:
                    problems.append(Problem(doc, link.line, target, reason))

        if remote:
            with ThreadPoolExecutor(max_workers=self.opts.workers) as pool:
                results = dict(zip(remote, pool.map(self.check_url, remote)))
            for url, reason in results.items():
                if reason:
                    soft = reason in {f"HTTP {s}" for s in SOFT_STATUSES}
                    for doc, link in remote[url]:
                        problems.append(Problem(doc, link.line, link.target, reason, warning=soft))

        problems.sort(key=lambda p: (str(p.file), p.line))
        return problems, total
