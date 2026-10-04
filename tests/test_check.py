import http.server
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from linkrot.check import Checker, Options, find_docs
from linkrot.cli import main


class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.respond(body=False)

    def do_GET(self):
        self.respond(body=True)

    def respond(self, body):
        if self.path == "/ok":
            code = 200
        elif self.path == "/no-head":
            code = 405 if self.command == "HEAD" else 200
        elif self.path == "/blocked":
            code = 403
        elif self.path == "/moved":
            self.send_response(301)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        else:
            code = 404
        self.send_response(code)
        self.send_header("Content-Length", "2" if body else "0")
        self.end_headers()
        if body:
            self.wfile.write(b"hi")

    def log_message(self, *args):
        pass


class Remote(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.checker = Checker(Options(timeout=5, retries=0))

    def test_ok_redirect_and_head_fallback(self):
        for path in ("/ok", "/moved", "/no-head"):
            with self.subTest(path=path):
                self.assertIsNone(self.checker.check_url(self.base + path))

    def test_404(self):
        self.assertEqual(self.checker.check_url(self.base + "/gone"), "HTTP 404")

    def test_bot_protection_warns_unless_strict(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "a.md"
            doc.write_text(f"[x]({self.base}/blocked)\n")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(doc), "--timeout", "5"]), 0)
                self.assertEqual(main([str(doc), "--timeout", "5", "--strict"]), 1)

    def test_connection_refused(self):
        self.assertIsNotNone(self.checker.check_url("http://127.0.0.1:9/"))


class Local(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "skip.md").write_text("[x](missing.md)")
        (self.root / "docs" / "guide.md").write_text("# Guide\n\n## Setup steps\n")
        (self.root / "README.md").write_text(
            "# Project\n\n"
            "[guide](docs/guide.md)\n"
            "[setup](docs/guide.md#setup-steps)\n"
            "[bad anchor](docs/guide.md#install)\n"
            "[missing](docs/nope.md)\n"
            "[self](#project)\n"
            "[mail](mailto:me@example.com)\n"
            "[ignored](https://localhost:3000/)\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_docs_skips_vendored_dirs(self):
        found = {p.relative_to(self.root).as_posix() for p in find_docs([self.root])}
        self.assertEqual(found, {"README.md", "docs/guide.md"})

    def test_cli_reports_only_broken_local_links(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(self.root), "--offline", "--json", "--ignore", "https://localhost*"])
        self.assertEqual(code, 1)
        problems = json.loads(out.getvalue())
        self.assertEqual(
            [(p["line"], p["link"], p["reason"]) for p in problems],
            [(5, "docs/guide.md#install", "no heading #install"), (6, "docs/nope.md", "file not found")],
        )

    def test_clean_tree_exits_zero(self):
        (self.root / "README.md").write_text("# Hi\n\n[guide](docs/guide.md)\n")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.root), "--offline"]), 0)


if __name__ == "__main__":
    unittest.main()
