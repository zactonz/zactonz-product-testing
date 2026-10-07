"""Ledger API — a small invoicing service. Run: python3 app.py [port]

DELIBERATELY INSECURE. This is a test fixture, not an example to learn from.

It contains, on purpose: a missing ownership check, mass assignment of privileged
columns, SQL injection through an ORDER BY clause, reflected XSS, unauthenticated
server-side request forgery, debug-mode stack traces, a non-atomic quota counter,
byte-wise truncation that corrupts multibyte text, an unbounded row limit, and
several UI faults. It exists so a test pass can be scored against known defects.

Bind it to loopback only, never to a shared or reachable host, and stop it when
you are done. All state is in memory, so restarting resets it — which is also how
to get a clean instance between evaluation runs. See ../README.md and
../GROUND-TRUTH.md.
"""
import http.server, json, sqlite3, sys, threading, time, traceback, urllib.request, html

DEBUG = True
TOKENS = {"tok-alice": 1, "tok-bob": 2}
DB = sqlite3.connect(":memory:", check_same_thread=False)
LOCK = threading.Lock()
DB.executescript("""
CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, is_admin INT DEFAULT 0, jobs_used INT DEFAULT 0);
CREATE TABLE invoices(id INTEGER PRIMARY KEY, user_id INT, amount INT, note TEXT);
CREATE TABLE items(id INTEGER PRIMARY KEY, user_id INT, label TEXT, price INT);
INSERT INTO users(id,name) VALUES (1,'alice'),(2,'bob');
INSERT INTO invoices(id,user_id,amount,note) VALUES
 (101,1,500,'alice invoice'),(102,2,9900,'bob CONFIDENTIAL salary invoice');
""")
for i in range(1, 61):
    DB.execute("INSERT INTO items(user_id,label,price) VALUES (?,?,?)", (1 + i % 2, f"item{i}", i * 10))
DB.commit()

QUOTA = 3
PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{background:#fff;color:#111;font-family:system-ui;margin:0;padding:24px}
 input{border:1px solid #ccc;padding:8px}
 input:focus{outline:none}
 .grid{width:420px;border-collapse:collapse}
 .grid td{border:1px solid #eee;padding:6px}
 @media (prefers-color-scheme:dark){ body{background:#111;color:#eee} .panel{background:#fff} }
 .panel{padding:12px;border-radius:6px}
</style></head><body>
<h2>Ledger</h2>
<form><input type="text" name="q" placeholder="Search invoices"><button>Go</button></form>
<div class="panel">Balance: 500</div>
<table class="grid"><tr><td>item1</td><td>10</td></tr><tr><td>item2</td><td>20</td></tr></table>
<script>document.addEventListener('DOMContentLoaded',function(){ window.ledgerInit(); });</script>
</body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LedgerAPI/2.4.1 Python/3"

    def reply(self, code, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def who(self):
        auth = self.headers.get("Authorization", "")
        return TOKENS.get(auth.replace("Bearer ", "").strip())

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/app":
                return self.reply(200, PAGE.encode(), "text/html; charset=utf-8")
            if u.path == "/health":
                return self.reply(200, {"ok": True})

            if u.path.startswith("/invoices/"):
                if not self.who():
                    return self.reply(401, {"error": "unauthenticated"})
                r = DB.execute("SELECT id,user_id,amount,note FROM invoices WHERE id=?",
                               (u.path.rsplit("/", 1)[1],)).fetchone()
                if not r:
                    return self.reply(404, {"error": "not_found"})
                return self.reply(200, {"id": r[0], "user_id": r[1], "amount": r[2], "note": r[3]})

            if u.path == "/items":
                uid = self.who()
                if not uid:
                    return self.reply(401, {"error": "unauthenticated"})
                limit = int(q.get("limit", 20))
                sort = q.get("sort", "id")
                sql = f"SELECT id,label,price FROM items WHERE user_id={uid} ORDER BY {sort}"
                if limit > 0:
                    sql += f" LIMIT {limit}"
                rows = DB.execute(sql).fetchall()
                return self.reply(200, {"count": len(rows),
                                        "items": [{"id": r[0], "label": r[1], "price": r[2]} for r in rows]})

            if u.path == "/search":
                term = q.get("q", "")
                page = f"<!DOCTYPE html><html><body><h3>Results for {term}</h3><p>0 found.</p></body></html>"
                return self.reply(200, page.encode(), "text/html; charset=utf-8")

            if u.path == "/preview":
                target = q.get("url", "")
                with urllib.request.urlopen(target, timeout=4) as r:
                    return self.reply(200, {"url": target, "status": r.status,
                                            "body": r.read(400).decode("utf-8", "replace")})

            return self.reply(404, {"error": "no_route"})
        except Exception:
            if DEBUG:
                return self.reply(500, {"error": "server_error", "trace": traceback.format_exc()})
            return self.reply(500, {"error": "server_error"})

    def do_POST(self):
        try:
            if self.path == "/jobs":
                uid = self.who()
                if not uid:
                    return self.reply(401, {"error": "unauthenticated"})
                used = DB.execute("SELECT jobs_used FROM users WHERE id=?", (uid,)).fetchone()[0]
                if used >= QUOTA:
                    return self.reply(429, {"error": "quota_exceeded", "used": used})
                time.sleep(0.04)
                DB.execute("UPDATE users SET jobs_used=? WHERE id=?", (used + 1, uid))
                DB.commit()
                return self.reply(201, {"queued": True, "used": used + 1})

            if self.path == "/profile":
                uid = self.who()
                if not uid:
                    return self.reply(401, {"error": "unauthenticated"})
                name = self.body().get("name", "")
                stored = name.encode()[:10].decode("utf-8", "ignore")
                DB.execute("UPDATE users SET name=? WHERE id=?", (stored, uid))
                DB.commit()
                return self.reply(200, {"name": stored, "bytes": len(name.encode())})
            return self.reply(404, {"error": "no_route"})
        except Exception:
            if DEBUG:
                return self.reply(500, {"error": "server_error", "trace": traceback.format_exc()})
            return self.reply(500, {"error": "server_error"})

    def do_PATCH(self):
        try:
            if self.path == "/me":
                uid = self.who()
                if not uid:
                    return self.reply(401, {"error": "unauthenticated"})
                patch = self.body()
                for field, value in patch.items():
                    DB.execute(f"UPDATE users SET {field}=? WHERE id=?", (value, uid))
                DB.commit()
                r = DB.execute("SELECT id,name,is_admin FROM users WHERE id=?", (uid,)).fetchone()
                return self.reply(200, {"id": r[0], "name": r[1], "is_admin": r[2]})
            return self.reply(404, {"error": "no_route"})
        except Exception:
            if DEBUG:
                return self.reply(500, {"error": "server_error", "trace": traceback.format_exc()})
            return self.reply(500, {"error": "server_error"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8910
    print(f"Ledger API on http://127.0.0.1:{port}  tokens: tok-alice (user 1), tok-bob (user 2)")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
