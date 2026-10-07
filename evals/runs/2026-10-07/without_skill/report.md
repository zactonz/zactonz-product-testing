# Ledger API — Test Pass Report

**Target:** http://127.0.0.1:8910 (Ledger API 2.4.1, Python http.server, in-memory SQLite)
**Date:** 2026-10-07
**Scope:** UI, functional, stress/concurrency, and security testing against the documented contract (README).
**Authorization:** Local throwaway fixture owned by the user; full testing (including load and security probing) authorized. Source not modified.

Tokens: tok-alice = user 1, tok-bob = user 2.

> Shared-state note: during testing, user 1 (alice) showed is_admin=1 though only bob was escalated in my own tests. A second evaluation run appears to share this process's in-memory DB. This does not affect any finding below — each was reproduced from my own requests and from source inspection.

---

## Summary of findings

| # | Severity | Endpoint | Defect |
|---|----------|----------|--------|
| 1 | Critical | GET /invoices/<id> | IDOR — any authenticated user can read any invoice (no owner check) |
| 2 | Critical | GET /items?sort= | SQL injection in ORDER BY; blind cross-user data exfiltration |
| 3 | Critical | PATCH /me | Mass assignment / privilege escalation (is_admin, jobs_used, id) + field-name SQLi |
| 4 | Critical | GET /preview?url= | SSRF + local file read via file:// (unauthenticated) |
| 5 | Critical | GET /search?q= | Reflected XSS (unescaped reflection into text/html) |
| 6 | High | POST /jobs | Quota race condition (TOCTOU); unused LOCK |
| 7 | High | all | Debug tracebacks leaked in 500 responses (DEBUG=True): stack traces, file paths, SQL errors |
| 8 | Medium | GET /items?limit= | limit not bounded: limit<=0 returns ALL rows; >100 accepted (contract is 1-100) |
| 9 | Medium | POST /profile | Name truncated to 10 bytes, not 10 characters (multibyte names wrongly cut) |
| 10 | Low | GET /app | UI calls undefined window.ledgerInit() -> JS error on every load |
| 11 | Low | GET /app | Dark-mode contrast: .panel white box with light text -> "Balance" unreadable |
| 12 | Low | GET /app | Search form has no action -> "Go" reloads /app, never hits /search |
| 13 | Low | auth | Raw token accepted without "Bearer " prefix (loose .replace) |
| 14 | Low | /items, /profile | No input validation -> unhandled 500 on non-integer limit and malformed JSON body |
| 15 | Low | all | Server header discloses software/version/stack (LedgerAPI/2.4.1 ... Python/3.14.8) |

**Counts:** Critical 5, High 2, Medium 2, Low 6 — 15 total.

---

## Critical

### 1. IDOR on GET /invoices/<id> — cross-tenant data exposure
README promise: "the caller's own invoice; 404 for anyone else's." The query filters by invoice id only, never by user_id.

    $ curl -s -H "Authorization: Bearer tok-alice" .../invoices/102
    {"id": 102, "user_id": 2, "amount": 9900, "note": "bob CONFIDENTIAL salary invoice"}

Alice reads Bob's confidential salary invoice (and vice versa). Any authenticated user can enumerate and read every invoice.

### 2. SQL injection in GET /items?sort= — blind cross-user exfiltration
sort is string-interpolated into "ORDER BY {sort}" with no validation (README allows only id, label, price).
- Arbitrary expression confirmed: sort=price DESC reorders results; invalid column sort=bogus returns sqlite3.OperationalError: no such column: bogus in a leaked traceback.
- Blind boolean oracle demonstrated against another user's data:
  - (SELECT amount FROM invoices WHERE id=102) > 1000   -> ascending [20,40,60,80]  (TRUE)
  - (SELECT amount FROM invoices WHERE id=102) > 100000  -> descending [600,580,560,540] (FALSE)

Allows exfiltration of arbitrary DB contents one bit at a time, for any authenticated user.

### 3. Mass assignment / privilege escalation on PATCH /me
README: "updates the caller's own name. No other field is user-editable." Handler loops over every JSON key and runs "UPDATE users SET {field}=? WHERE id=?".

    $ curl -s -X PATCH -H "Authorization: Bearer tok-bob" -d '{"is_admin":1}' .../me
    {"id": 2, "name": "bobby", "is_admin": 1}          # self-promotion to admin
    $ curl -s -X PATCH -H "Authorization: Bearer tok-bob" -d '{"jobs_used":0}' .../me   # resets own quota
    $ curl -s -X PATCH -H "Authorization: Bearer tok-bob" -d '{"id":99}' .../me          # corrupts identity

The field name is also interpolated into SQL, so the key is a second SQL-injection vector. Impact: arbitrary privilege escalation, quota reset, account corruption.

### 4. SSRF + local file read on GET /preview?url= (unauthenticated)
No scheme/host allow-listing; urllib.request.urlopen is called on attacker input.

    $ curl -s ".../preview?url=http://127.0.0.1:8910/health"   # fetches internal loopback service
    {"url": "...", "status": 200, "body": "{\"ok\": true}"}
    $ curl -s ".../preview?url=file:///etc/passwd"             # arbitrary local file read
    {"url": "file:///etc/passwd", "status": null, "body": "[redacted: the file's contents were returned verbatim]"}

Unauthenticated attacker can reach internal-only services (e.g. cloud metadata) and read local files via file://.

### 5. Reflected XSS on GET /search?q=
q is reflected verbatim into an HTML document served as text/html; the imported html module is never used to escape it.

    $ curl -s ".../search?q=<script>alert(1)</script>"
    <!DOCTYPE html>...<h3>Results for <script>alert(1)</script></h3>...

Any crafted link executes script in the victim's browser.

---

## High

### 6. POST /jobs quota race condition (TOCTOU)
README: at most 3 queued; the 4th returns 429. Serially this holds (3x 201, then 429). But the handler does a non-atomic read-modify-write around time.sleep(0.04), and the module-level LOCK is never acquired.

    # after resetting jobs_used=0, fire 10 concurrent requests:
       8 201
       2 500

8 jobs queued against a limit of 3. The intermittent 500s indicate SQLite write contention under concurrency (secondary robustness issue from the same lack of locking).

### 7. Debug tracebacks leaked on errors (DEBUG=True)
Every unhandled error returns the full Python traceback, including absolute source paths and SQL error detail, e.g.:

    {"error": "server_error", "trace": "Traceback ... /private/tmp/.../fixture/app.py, line 88 ...
     sqlite3.OperationalError: no such column: bogus"}

Observed on /items (bad sort / non-int limit), /me (SQLi/bad field), /profile (bad JSON), /preview (bad URL). Leaks internal paths and aids exploitation of the injection flaws above.

---

## Medium

### 8. GET /items?limit= not bounded (contract: 1-100, default 20)
No clamping. Code only appends LIMIT when limit > 0, so non-positive values return the entire result set:

    limit=0  -> count 30 (all rows)
    limit=-5 -> count 30 (all rows)
    limit=99999999 -> 200 OK (accepted, no upper clamp)

Contract violation and a potential resource-exhaustion vector on larger tables.

### 9. POST /profile truncates by bytes, not characters
README: "max 10 characters." Code does name.encode()[:10] (10 bytes):

    "0123456789ABCDE" (15 chars) -> "0123456789"  (ok for ASCII)
    emoji x10 (10 chars, 40 bytes) -> 2 emoji       # over-truncated
    "e-acute" x5 (5 chars, 10 bytes) -> all 5; 6 would be cut to 5

Any name using multibyte characters is truncated well below the documented 10-character limit.

---

## Low

- 10. Undefined UI init (GET /app): page runs window.ledgerInit() on DOMContentLoaded but it is never defined. Console shows "Uncaught TypeError: window.ledgerInit is not a function" on every load; the UI init always fails.
- 11. Dark-mode contrast (GET /app): dark media query sets body text to light #eee but overrides .panel{background:#fff} without a dark text color, rendering "Balance: 500" as near-white text on a white box (unreadable). Verified visually in emulated dark mode.
- 12. Non-functional search form (GET /app): the <form> has no action, so submitting reloads /app?q=... (which ignores q) instead of calling /search. The UI search box does nothing useful.
- 13. Loose auth parsing: who() uses auth.replace("Bearer ", "").strip(), so a raw token with no scheme is accepted: Authorization: tok-alice -> 200. The Bearer scheme is not enforced.
- 14. Missing input validation -> 500s: limit=abc and a malformed JSON body (/profile, /me) raise unhandled exceptions (500) rather than 400. Combined with #7 this leaks tracebacks.
- 15. Verbose Server header: "Server: LedgerAPI/2.4.1 Python/3 Python/3.14.8" discloses software name, version, and interpreter version.

---

## Test coverage notes
- Functional: health, invoice fetch (own/other/missing/unauth), items (sort/limit happy + edge), jobs quota (sequential), profile length, me name update — all exercised.
- Security: IDOR, SQLi (two injection points, incl. blind exfil PoC), mass assignment, SSRF/LFI, reflected XSS, auth parsing, info disclosure.
- Stress/concurrency: 10-12 concurrent /jobs bursts after quota reset; confirmed race and write contention.
- UI: rendered /app in light and dark, captured console error and the dark-mode contrast failure.

## Evidence files (this directory)
- report.md — this report
- codes.txt, out.txt — raw HTTP status/body captures from the concurrency runs

All curl commands above are reproducible against the running instance.
