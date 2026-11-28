"""Serve the portable composition lab and collect only allowlisted, anonymous counters."""
import argparse
import base64
import hmac
import html
import json
import os
from pathlib import Path
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
DB = Path(os.environ.get("FRAME_DB", str(ROOT / "var" / "events.sqlite3"))).resolve()
EVENTS = {"page_view", "demo_start", "export_completed", "download_clicked"}
FIXED = {"content": "three-frames", "variant": "signal-desk", "campaign": "field-notes"}

def connect():
    return sqlite3.connect(DB, timeout=5)

def initialize():
    if DB == SITE or SITE in DB.parents:
        raise ValueError("Choose a database path outside the static site.")
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS events
            (id INTEGER PRIMARY KEY, day TEXT DEFAULT (date('now')), name TEXT NOT NULL,
            content TEXT NOT NULL, variant TEXT NOT NULL, campaign TEXT NOT NULL, traffic TEXT NOT NULL)""")

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def log_message(self, *args):
        pass  # Do not retain addresses, URLs or input values.

    def list_directory(self, path):
        self.send_error(404)

    def reply(self, status, payload=b"", mime="text/plain; charset=utf-8", auth=False):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if auth:
            self.send_header("WWW-Authenticate", 'Basic realm="Frame lab", charset="UTF-8"')
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def admin(self):
        secret = os.environ.get("FRAME_ADMIN_PASSWORD")
        if not secret:
            return self.reply(503, b"Admin is disabled.")
        expected = b"Basic " + base64.b64encode(("admin:" + secret).encode())
        if not hmac.compare_digest(self.headers.get("Authorization", "").encode(), expected):
            return self.reply(401, b"Authentication required.", auth=True)
        with connect() as conn:
            rows = conn.execute("""SELECT day,name,content,variant,campaign,traffic,count(*)
                FROM events GROUP BY day,name,content,variant,campaign,traffic
                ORDER BY day DESC, traffic, name""").fetchall()
        header = ["UTC day","Event","Content","Variant","Campaign","Traffic","Count"]
        table = "<tr>"+"".join("<th scope=col>"+name+"</th>" for name in header)+"</tr>"
        for row in rows:
            table += "<tr>"+"".join("<td>"+html.escape(str(v))+"</td>" for v in row)+"</tr>"
        body = '<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width, initial-scale=1"><title>Frame lab counts</title><link rel=stylesheet href=/style.css><main><h1>Lab counts</h1><p>Anonymous event totals by UTC day. Test traffic has its own rows.</p><div style="overflow:auto"><table cellpadding=6>'+table+"</table></div></main></html>"
        self.reply(200, body.encode(), "text/html; charset=utf-8")

    def do_GET(self):
        if urlsplit(self.path).path.rstrip("/") == "/admin":
            return self.admin()
        return super().do_GET()

    def do_HEAD(self):
        if urlsplit(self.path).path.rstrip("/") == "/admin":
            return self.admin()
        return super().do_HEAD()

    def do_POST(self):
        if self.path != "/events":
            return self.reply(404)
        if self.headers.get_content_type() != "application/json":
            return self.reply(415)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 512:
                return self.reply(400)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or set(data) != set(FIXED) | {"name","traffic"}:
                return self.reply(400)
            if any(data[k] != v for k,v in FIXED.items()) or data["name"] not in EVENTS or data["traffic"] not in {"test","standard"}:
                return self.reply(400)
        except (ValueError, TypeError, UnicodeError):
            return self.reply(400)
        with connect() as conn:
            conn.execute("INSERT INTO events(name,content,variant,campaign,traffic) VALUES (?,?,?,?,?)",
                tuple(data[k] for k in ("name","content","variant","campaign","traffic")))
        self.reply(204)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    initialize()
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()

