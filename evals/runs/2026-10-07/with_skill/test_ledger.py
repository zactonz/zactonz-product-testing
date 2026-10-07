#!/usr/bin/env python3
"""Regression suite for the Ledger API.

Standard library only. Point it at a running instance:

    python3 app.py 8910            # in the fixture dir, in another shell
    LEDGER_URL=http://127.0.0.1:8910 python3 -m unittest test_ledger -v

Every test named ``test_FNN_*`` encodes a confirmed finding from the
2026-10-07 test pass and FAILS against the current code; it flips to green when
the matching fix lands. The ``test_ok_*`` tests document behaviour that already
holds and should keep holding.
"""
import json, os, threading, unittest, urllib.error, urllib.request

BASE = os.environ.get("LEDGER_URL", "http://127.0.0.1:8910").rstrip("/")
ALICE = {"Authorization": "Bearer tok-alice"}
BOB = {"Authorization": "Bearer tok-bob"}


def req(method, path, headers=None, body=None):
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers or {})
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def reset_jobs(headers):
    # Uses PATCH /me (itself buggy) only as test setup to zero the counter.
    req("PATCH", "/me", {**headers, "Content-Type": "application/json"}, {"jobs_used": 0})


class Sanity(unittest.TestCase):
    def test_ok_health(self):
        code, body = req("GET", "/health")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), {"ok": True})

    def test_ok_unauth_invoice_401(self):
        code, _ = req("GET", "/invoices/101")
        self.assertEqual(code, 401)

    def test_ok_serial_quota(self):
        reset_jobs(ALICE)
        codes = [req("POST", "/jobs", ALICE)[0] for _ in range(4)]
        self.assertEqual(codes, [201, 201, 201, 429])
        reset_jobs(ALICE)


class Findings(unittest.TestCase):
    def test_F01_invoices_bola(self):
        """Alice must NOT read Bob's invoice (README: 404 for anyone else's)."""
        code, body = req("GET", "/invoices/102", ALICE)  # 102 belongs to user 2
        self.assertIn(code, (403, 404), f"cross-account read allowed: {code} {body}")

    def test_F02_patch_me_rejects_is_admin(self):
        """PATCH /me must ignore non-name fields (README: no other field editable)."""
        req("PATCH", "/me", {**ALICE, "Content-Type": "application/json"}, {"is_admin": 0})
        code, body = req("PATCH", "/me", {**ALICE, "Content-Type": "application/json"}, {"is_admin": 1})
        self.assertEqual(json.loads(body).get("is_admin"), 0,
                         "is_admin is user-editable (privilege escalation)")

    def test_F03_items_sort_not_injectable(self):
        """sort must be allowlisted; an arbitrary SQL expression must be rejected."""
        code, body = req("GET", "/items?sort=note", ALICE)  # column not in items
        self.assertNotEqual(code, 500, "sort is interpolated into SQL (injection)")
        self.assertIn(code, (400, 422), f"unknown sort not rejected cleanly: {code}")

    def test_F03b_items_sort_blind_injection_inert(self):
        """A subquery in sort must not change results (proves it is not executed)."""
        true_q = "CASE WHEN (SELECT COUNT(*) FROM users)>0 THEN label ELSE id END"
        false_q = "CASE WHEN (SELECT COUNT(*) FROM users)>99 THEN label ELSE id END"
        from urllib.parse import quote
        _, b1 = req("GET", f"/items?limit=4&sort={quote(true_q)}", ALICE)
        _, b2 = req("GET", f"/items?limit=4&sort={quote(false_q)}", ALICE)
        # If injection is fixed both are errors/identical; today they differ.
        if b1.startswith("{") and "items" in b1 and b2.startswith("{") and "items" in b2:
            o1 = [i["label"] for i in json.loads(b1)["items"]]
            o2 = [i["label"] for i in json.loads(b2)["items"]]
            self.assertEqual(o1, o2, "ORDER BY subquery executed: blind SQL injection")

    def test_F04_preview_rejects_file_scheme(self):
        from urllib.parse import quote
        code, body = req("GET", "/preview?url=" + quote("file:///etc/passwd"), None)
        self.assertNotEqual(code, 200, "file:// scheme fetched (local file read)")

    def test_F04b_preview_rejects_loopback(self):
        from urllib.parse import quote
        code, body = req("GET", "/preview?url=" + quote("http://127.0.0.1:8910/health"), None)
        self.assertNotEqual(code, 200, "loopback fetched (SSRF)")

    def test_F05_search_escapes_html(self):
        code, body = req("GET", "/search?q=%3Cscript%3E")
        self.assertNotIn("<script>", body, "q reflected unescaped (reflected XSS)")

    def test_F06_errors_leak_no_trace(self):
        from urllib.parse import quote
        code, body = req("GET", "/preview?url=" + quote("http://nonexistent.invalid.local/"), None)
        self.assertNotIn("Traceback", body, "stack trace leaked in error body (DEBUG on)")
        self.assertNotIn("app.py", body)

    def test_F07_jobs_quota_atomic(self):
        reset_jobs(ALICE)
        n, out = 15, [0] * 15
        def fire(i):
            out[i] = req("POST", "/jobs", ALICE)[0]
        ts = [threading.Thread(target=fire, args=(i,)) for i in range(n)]
        [t.start() for t in ts]; [t.join() for t in ts]
        queued = out.count(201)
        reset_jobs(ALICE)
        self.assertLessEqual(queued, 3, f"{queued} jobs queued under concurrency (quota=3): race")

    def test_F08_db_endpoint_stable_under_concurrency(self):
        n, out = 60, [0] * 60
        def fire(i):
            out[i] = req("GET", "/items?limit=20", ALICE)[0]
        ts = [threading.Thread(target=fire, args=(i,)) for i in range(n)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(out.count(500), 0,
                         f"{out.count(500)}/{n} reads 500ed (shared sqlite connection, LOCK unused)")

    def test_F09_items_limit_range_enforced(self):
        c0, b0 = req("GET", "/items?limit=0", ALICE)
        self.assertNotEqual(json.loads(b0).get("count"), 30,
                            "limit=0 returns all rows (LIMIT clause dropped)")

    def test_F10_profile_limit_is_characters(self):
        nine = "α" * 9  # 9 Greek chars, 18 bytes
        code, body = req("POST", "/profile", {**BOB, "Content-Type": "application/json"}, {"name": nine})
        stored = json.loads(body).get("name", "")
        req("POST", "/profile", {**BOB, "Content-Type": "application/json"}, {"name": "bob"})
        self.assertEqual(len(stored), 9, "name truncated to bytes, not characters")

    def test_F11_malformed_json_is_4xx(self):
        code, body = req("POST", "/profile", {**ALICE, "Content-Type": "application/json"}, b"{not json")
        self.assertNotEqual(code, 500, "malformed JSON returns 500 instead of 400")

    def test_F12_auth_requires_bearer_scheme(self):
        code, _ = req("GET", "/invoices/101", {"Authorization": "tok-alice"})  # no 'Bearer '
        self.assertEqual(code, 401, "token accepted without Bearer scheme (loose parsing)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
