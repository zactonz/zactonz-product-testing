# Test report — Ledger API 2.4.1

**Tested** 2026-10-07 · **Build** `app.py` as served at the time of test (no VCS tag; `server_version` string `LedgerAPI/2.4.1`) · **Environment** local, `http://127.0.0.1:8910`, Python 3.14.8, macOS (Darwin 25.6.0), in-memory SQLite, `DEBUG=True`
**Dimensions** functionality, ui, load, security (all four)
**Harness** `curl` + Python 3 stdlib (`urllib`, `threading`); `test_ledger.py` (unittest); bundled `loadtest.py`; built-in browser for the UI page

> Note: a second test run shared this instance throughout (stated in the task). It
> independently exercised the mass-assignment bug (F2) and changed user 2's `id`,
> so Bob's account 500s on `/jobs` and `/me` for the duration. Quota and account
> tests were therefore run as Alice (user 1). This is noted again under Not tested.

## Verdict

Do not ship. The API exposes four independent critical flaws reachable by an
ordinary token or no token at all: any authenticated user can read any other
account's invoices (BOLA), any user can make themselves admin and rewrite
arbitrary columns (mass assignment), the `/items` sort parameter is a live SQL
injection, and the unauthenticated `/preview` endpoint is a full SSRF with local
file read. Four further High issues (reflected XSS, unauthenticated stack-trace
disclosure, a quota that collapses under concurrency, and DB endpoints that 500
intermittently under normal concurrency) compound it. Every finding below was
reproduced with captured output.

| Severity | Count |
|---|---|
| Critical | 4 |
| High | 4 |
| Medium | 5 |
| Low | 4 |

## Findings

### F1 · Critical · `GET /invoices/<id>` returns any account's invoice to any authenticated caller (BOLA)

**Surface** `GET /invoices/<id>` — `app.py:79-85`

**Reproduction**
```bash
curl -s -H 'Authorization: Bearer tok-alice' http://127.0.0.1:8910/invoices/102
```

**Observed** `200` — `{"id": 102, "user_id": 2, "amount": 9900, "note": "bob CONFIDENTIAL salary invoice"}`. Alice (user 1) reads Bob's (user 2) invoice. Reproduced 4/4 (and the symmetric Bob→101 case). Unauthenticated access is correctly `401`; a non-existent id is `404`.

**Expected** `404` for another user's invoice — README: "the caller's own invoice; 404 for anyone else's."

**Why it matters** The handler checks `who()` (authenticated) but never compares `invoices.user_id` to the caller. Any valid token reads every invoice by sequential integer id — a complete cross-tenant data breach of financial records.

**Evidence** `evidence/F-invoices-idor.txt`

**Fix** Scope the query: `... WHERE id=? AND user_id=?` with `(id, who())`, at `app.py:81`.

### F2 · Critical · `PATCH /me` is mass-assignable — any user can set `is_admin`, `jobs_used`, `id`, any column

**Surface** `PATCH /me` — `app.py:140-150`

**Reproduction**
```bash
curl -s -X PATCH -H 'Authorization: Bearer tok-alice' -H 'Content-Type: application/json' \
  -d '{"is_admin":1}' http://127.0.0.1:8910/me
```

**Observed** `200` — `{"id":1,"name":"alice","is_admin":1}`. Toggling the sent value 0→1→0 flips the stored value each time (3/3). Sending `{"jobs_used":0}` resets the job quota. The shared parallel run sent an `id` change to user 2, which removed its row and now 500s `/jobs` and `/me` for that user — demonstrating account corruption from the same bug.

**Expected** Only `name` is editable — README: "No other field is user-editable."

**Why it matters** The handler loops over every key in the body and interpolates it straight into `UPDATE users SET {field}=?`. This is a full privilege escalation (`is_admin`), a quota bypass (`jobs_used`), account takeover/corruption (`id`), and — because the column name is interpolated, not parameterised — a second SQL-injection point. `is_admin` has no consumer today, so the escalation is latent, but the field the product tracks for admin is attacker-controlled.

**Evidence** `evidence/F-me-massassign.txt`, `evidence/F-me-massassign-toggle.txt`

**Fix** Allowlist editable fields (`{"name"}`) and reject anything else with `400`; never interpolate a key into SQL. `app.py:144-146`.

### F3 · Critical · `GET /items?sort=` is SQL-injectable via `ORDER BY`

**Surface** `GET /items?limit=&sort=` — `app.py:86-91` (`sql = f"... ORDER BY {sort}"`)

**Reproduction**
```bash
# Error-based: proves raw interpolation
curl -s -H 'Authorization: Bearer tok-alice' 'http://127.0.0.1:8910/items?sort=note'
# Blind boolean: ordering changes with a subquery over another table
curl -s -G -H 'Authorization: Bearer tok-alice' --data-urlencode \
  'sort=CASE WHEN (SELECT COUNT(*) FROM users)>0 THEN label ELSE id END' --data-urlencode 'limit=4' \
  http://127.0.0.1:8910/items
curl -s -G -H 'Authorization: Bearer tok-alice' --data-urlencode \
  'sort=CASE WHEN (SELECT COUNT(*) FROM users)>99 THEN label ELSE id END' --data-urlencode 'limit=4' \
  http://127.0.0.1:8910/items
```

**Observed** `sort=note` → `500` leaking `sqlite3.OperationalError: no such column: note`. The two blind payloads return different orderings (`[item10,item12,...]` vs `[item2,item4,...]`), proving a subquery over the `users` table is executed from request input. Reproduced 2/2 and 1/1 respectively.

**Expected** `sort` is one of `id`, `label`, `price` (README); anything else rejected with `400`.

**Why it matters** `sort` is concatenated into the query. Parameterisation does not cover identifiers/`ORDER BY`, so this is exploitable for blind and error-based extraction of any table (users, invoices) the connection can read — independent of the per-user scoping the rest of the endpoint applies.

**Evidence** `evidence/F-items-sqli.txt`

**Fix** Map `sort` through an allowlist to a fixed column name before building the SQL; reject unknown values. `app.py:89`.

### F4 · Critical · `GET /preview?url=` is an unauthenticated SSRF with arbitrary local file read

**Surface** `GET /preview?url=` — `app.py:97-101` (`urllib.request.urlopen(target)`)

**Reproduction**
```bash
# Local file read (no auth):
curl -s -G --data-urlencode 'url=file:///etc/passwd' http://127.0.0.1:8910/preview
# Internal/loopback fetch (no auth):
curl -s -G --data-urlencode 'url=http://127.0.0.1:8910/health' http://127.0.0.1:8910/preview
```

**Observed** `file://` returns the target file's contents in the `body` field (proved by reading the fixture's own README, `status:null`, `200`). The loopback fetch returns the internal response body (`200`, 3/3). A request for `http://169.254.169.254/` is attempted (fails only because this host has no metadata service — `No route to host`), proving there is no address allow-list.

**Expected** "fetches a **public** URL" (README) — private/loopback/link-local addresses and non-HTTP schemes refused.

**Why it matters** No scheme or address validation. Unauthenticated callers can read local files (`file://`), reach internal-only services, and hit cloud metadata endpoints. The response body is echoed back verbatim, so it is a direct read primitive, not blind.

**Evidence** `evidence/F-preview-ssrf.txt`, `evidence/F-preview-filescheme.txt`

**Fix** Allow only `http`/`https`; resolve the host and reject loopback, link-local and RFC-1918 ranges (re-check after redirects); bound size and redirects. Require auth. `app.py:98`.

### F5 · High · Reflected XSS in `GET /search?q=`

**Surface** `GET /search?q=` — `app.py:92-96`

**Reproduction**
```bash
curl -s 'http://127.0.0.1:8910/search?q=%3Cscript%3Ealert(1)%3C/script%3E'
```

**Observed** `200`, body `...<h3>Results for <script>alert(1)</script></h3>...` — the term is reflected into HTML unescaped, served as `text/html`. Reproduced 2/2. (`html` is imported at `app.py:1` but never used to escape.)

**Expected** User input escaped before being placed in HTML.

**Why it matters** Unauthenticated reflected XSS: a crafted link executes attacker script in a victim's browser against this origin. There are no mitigating response headers (see F16).

**Evidence** `evidence/F-search-xss.txt`

**Fix** `html.escape(term)` before interpolation at `app.py:94`.

### F6 · High · Debug mode leaks full stack traces (paths, SQL, versions) on every error, unauthenticated

**Surface** all handlers — `DEBUG = True` at `app.py:4`; `traceback.format_exc()` in every `except` (`app.py:107-109`, `133-135`, `152-154`)

**Reproduction**
```bash
curl -s -G --data-urlencode 'url=http://nonexistent.invalid.local/' http://127.0.0.1:8910/preview
```

**Observed** `500` with a `trace` field containing the full Python traceback: absolute source paths (`/private/tmp/.../app.py`), the interpreter path and version, library internals, and (for `/items`) the SQL statement. Reachable unauthenticated via `/preview`. Observed on every provoked 500 across the run.

**Expected** Generic error body; no internal detail.

**Why it matters** Hands an attacker the file layout, dependency versions and query structure that make the other findings easier to exploit. Fix is one line.

**Evidence** `evidence/F-preview-ssrf.txt`, `evidence/F-misc-contract.txt`

**Fix** `DEBUG = False` for anything deployed; return `{"error":"server_error"}` only. `app.py:4`.

### F7 · High · `POST /jobs` quota collapses under concurrency (non-atomic counter)

**Surface** `POST /jobs` — `app.py:112-124` (read `jobs_used`, `time.sleep(0.04)`, write `used+1`)

**Reproduction**
```bash
# reset, then fire 15 concurrent POSTs against quota=3
python3 evidence/race.py 15
```

**Observed** 12–14 of 15 concurrent requests returned `201` (quota is 3), 0 returned `429`; the `used` values returned collapse to `{1}` or `{1,2}` — a classic lost-update race. Reproduced 3/3. Serially the quota is correct (`201,201,201,429,429`).

**Expected** At most 3 succeed; README: "Each user may queue at most 3; the 4th returns 429."

**Why it matters** The read-modify-write on `jobs_used` is not atomic and the module-level `LOCK` (`app.py:7`) is never acquired. Any rate/cost control built this way is bypassable by firing requests in parallel.

**Evidence** `evidence/F-jobs-race.txt`, `evidence/F-jobs-quota-serial.txt`

**Fix** Make it atomic: `UPDATE users SET jobs_used=jobs_used+1 WHERE id=? AND jobs_used<3` and check the affected row count, or hold `LOCK` around the read-write. `app.py:115-121`.

### F8 · High · DB-touching endpoints 500 intermittently under ordinary concurrency (unsafe shared SQLite connection)

**Surface** all DB handlers — single shared connection `DB` with `check_same_thread=False` (`app.py:6`) served by `ThreadingHTTPServer` (`app.py:160`); `LOCK` never used

**Reproduction**
```bash
python3 scripts/loadtest.py 'http://127.0.0.1:8910/items?limit=20' \
  -c 50 -d 6 -H 'Authorization: Bearer tok-alice'
```

**Observed** `/items` under `-c 50`: 46 of 9271 requests (0.5%) returned `500`; direct bursts reproduce it (e.g. 2/80, 1/60). Captured causes: `sqlite3.InterfaceError: bad parameter or other API misuse` and `IndexError: tuple index out of range` — symptoms of one cursor/connection used concurrently across threads. `/health` (no DB) ran 230k+ requests at `-c 25/50/100` with **0** errors, isolating the cause to shared DB access.

**Expected** No 500s on well-formed reads under normal concurrency.

**Why it matters** Every authenticated endpoint touches `DB`, so a small fraction of ordinary requests fail intermittently in production the moment there is parallel traffic — the kind of flaky failure that is hard to diagnose later.

**Evidence** `evidence/F-concurrency-thread-safety.txt`, `load/items-50.json`, `load/load-25.json`

**Fix** Use a connection per thread (or a pool), or serialise all DB access through the existing `LOCK`. `app.py:6-7`.

### F9 · Medium · `GET /items?limit=` ignores the documented 1–100 range

**Surface** `GET /items?limit=` — `app.py:84-85` (`if limit > 0: sql += LIMIT`)

**Reproduction**
```bash
curl -s -H 'Authorization: Bearer tok-alice' 'http://127.0.0.1:8910/items?limit=0'
curl -s -H 'Authorization: Bearer tok-alice' 'http://127.0.0.1:8910/items?limit=abc'
```

**Observed** `limit=0` and `limit=-1` return **all** of the user's rows (30) — the `LIMIT` clause is dropped. `limit=101` and `limit=1000` are accepted (return all 30). `limit=abc` → `500` (uncaught `int()` ValueError). Reproduced 1/1 each.

**Expected** `limit` is 1–100 (README); out-of-range rejected, non-numeric → 400.

**Why it matters** The documented cap is unenforced: `0`/negative become "return everything", which in a real dataset is an unbounded response and a cheap resource-exhaustion lever; non-numeric input crashes the handler.

**Evidence** `evidence/F-items-limit.txt`

**Fix** Parse `limit` safely, clamp/validate to 1–100, return `400` on non-numeric. `app.py:84`.

### F10 · Medium · `POST /profile` truncates to 10 bytes, not 10 characters (silent corruption)

**Surface** `POST /profile` — `app.py:129` (`name.encode()[:10].decode("utf-8","ignore")`)

**Reproduction**
```bash
curl -s -X POST -H 'Authorization: Bearer tok-alice' -H 'Content-Type: application/json' \
  -d '{"name":"ααααααααα"}' http://127.0.0.1:8910/profile
```

**Observed** A 9-character Greek name (18 bytes) is stored as 5 characters; 4 emoji (16 bytes) store as 2. The trailing partial code unit is dropped by `decode(...,"ignore")`. Reproduced 1/1 each.

**Expected** "max 10 **characters**" (README) — a 9-character name should be stored intact.

**Why it matters** Silent data loss: any non-ASCII display name is quietly mangled, with no error. Silent wrongness is worse than a rejection.

**Evidence** `evidence/F-profile-truncate.txt`

**Fix** Measure and slice by characters (`name[:10]`), or validate length and reject over-long input. `app.py:129`.

### F11 · Medium · `GET /app` throws on load — `window.ledgerInit is not a function`

**Surface** `GET /app` — inline script at `app.py:36` calls `window.ledgerInit()`, which is defined nowhere in the source

**Reproduction** Load `http://127.0.0.1:8910/app` in a browser; read the console.

**Observed** Console: `Uncaught TypeError: window.ledgerInit is not a function at .../app:16`. The static chrome renders (heading, search box, hardcoded "Balance: 500" and two static rows), but the page's only script fails on every load. Reproduced on load.

**Expected** No JavaScript error; the init routine runs.

**Why it matters** The one script on the page is dead, so any intended dynamic behaviour never initialises. Rendered content is static placeholder, not real data.

**Evidence** `evidence/F-ui-app-render.jpg`, `evidence/F-suite-run.txt` (console captured in session)

**Fix** Define `window.ledgerInit`, or remove the call. `app.py:36`.

### F12 · Medium · The UI search form never reaches `/search`

**Surface** `GET /app` — `<form>` at `app.py:34` has no `action` (and no `method`)

**Reproduction** On `/app`, type a term and click "Go"; observe the resulting URL.

**Observed** The form submits to `http://127.0.0.1:8910/app?q=alice` — the current page — not to `/search`. `/app` ignores `q` and re-serves the static page, so no results heading appears. Reproduced via the browser.

**Expected** The search box queries `/search` and shows results.

**Why it matters** The primary (only) interactive control on the UI does nothing. The `/search` endpoint — the one with the XSS (F5) — is only reachable by hand-crafted URL, but the UI's search is simply broken.

**Evidence** confirmed in-session (`location.href` = `/app?q=alice`, no `<h3>` results heading)

**Fix** Add `action="/search" method="get"` to the form. `app.py:34`.

### F13 · Medium · Invalid input returns 500 instead of a 4xx validation error

**Surface** `POST /profile`, `PATCH /me`, `POST /jobs`, `GET /items` — `body()` at `app.py:56-58` and unguarded parsing

**Reproduction**
```bash
curl -s -X POST -H 'Authorization: Bearer tok-alice' -H 'Content-Type: application/json' \
  -d '{not json' http://127.0.0.1:8910/profile
```

**Observed** Malformed JSON → `500` (`json.JSONDecodeError`); `/items?limit=abc` → `500`; `/items?sort=badcol` → `500`. Reproduced 1/1 each.

**Expected** `400` with an actionable message. A `500` tells the client to retry something that will never succeed.

**Why it matters** Distinct from F6 (which is the trace leak): even with debug off, ordinary bad input crashes the handler instead of being validated. Separate fix (input validation vs. disabling debug).

**Evidence** `evidence/F-misc-contract.txt`, `evidence/F-items-limit.txt`

**Fix** Catch parse errors and validation failures and return `400`; validate `limit`/`sort` before use.

### F14 · Low · Token accepted without the `Bearer` scheme (loose auth parsing)

**Surface** `who()` — `app.py:52-54` (`auth.replace("Bearer ", "")`)

**Reproduction**
```bash
curl -s -H 'Authorization: tok-alice' http://127.0.0.1:8910/invoices/101
curl -s -H 'Authorization: Bearer Bearer tok-alice' http://127.0.0.1:8910/invoices/101
```

**Observed** Both authenticate (`200`), as does a trailing `tok-aliceBearer `. `replace` strips `"Bearer "` wherever it appears rather than requiring it as a prefix. A genuinely wrong token is correctly `401`. Reproduced 1/1 each.

**Expected** A bearer token presented per RFC 6750 (`Authorization: Bearer <token>`).

**Why it matters** Low on its own — a valid token value is still required — but loose parsing can diverge from a proxy/WAF that only recognises a well-formed header, and it is a latent correctness smell.

**Evidence** `evidence/F-auth-substring.txt`

**Fix** Require and strip a literal `Bearer ` prefix; reject otherwise. `app.py:53`.

### F15 · Low · Server banner discloses product and runtime versions

**Surface** response headers — `server_version = "LedgerAPI/2.4.1 Python/3"` (`app.py:42`)

**Observed** `Server: LedgerAPI/2.4.1 Python/3 Python/3.14.8` on every response.

**Why it matters** Gives an attacker a precise version to match against known advisories. Combined with F6, fingerprinting is trivial.

**Evidence** `evidence/F-misc-contract.txt`

**Fix** Set a generic or empty `server_version`.

### F16 · Low · No security response headers on HTML responses

**Surface** `GET /app`, `GET /search` — `reply()` sets only `Content-Type`/`Content-Length` (`app.py:44-50`)

**Observed** None of `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security` are present.

**Why it matters** A CSP would blunt the reflected XSS in F5; `nosniff`/`X-Frame-Options` are cheap hardening. Low because they are defence-in-depth, not the root cause.

**Evidence** `evidence/F-misc-contract.txt`

**Fix** Add `X-Content-Type-Options: nosniff`, a restrictive CSP, and `X-Frame-Options: DENY` to HTML responses.

## Load results

| Scenario | Conc | Duration | Req/s | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|---|---|
| `/health` baseline | 1 | 50 req | 98 | 0.2ms | 0.2ms | 4.6ms | 0% |
| `/health` load | 25 | 8s | 12,950 | 1.7ms | 4.1ms | 5.7ms | 0% |
| `/health` stress | 50 | 6s | 13,150 | 3.2ms | 8.4ms | 11.5ms | 0% |
| `/health` stress | 100 | 6s | 11,152 | 7.1ms | 18.9ms | 27.6ms | 0% |
| `/items` (DB read) | 50 | 6s | 1,528 | 31ms | 58.6ms | 93ms | **0.5% (500s)** |

**Capacity** The no-DB path (`/health`) is very fast and stable to ~13k req/s with no errors; the real ceiling is the single shared SQLite connection, which both caps DB-endpoint throughput at ~1.5k req/s and makes ~0.5% of concurrent DB requests fail with 500s (F8). The bottleneck is DB access serialisation, not CPU or the HTTP layer.
**Environment** macOS (Darwin 25.6.0), Python 3.14.8, in-memory SQLite, `DEBUG=True` (debug tracebacks add per-error cost), local loopback (no network). Generated with the bundled `loadtest.py`.

## Verified working

- `GET /health` → `{"ok":true}`, and stable under sustained/stress load (0 errors over 230k+ requests).
- Authentication gate: unauthenticated calls to `/invoices`, `/items`, `/jobs`, `/profile`, `/me` return `401`; a wrong token returns `401`.
- `/invoices/<id>` returns `404` for a non-existent id and for a non-integer id (no crash there).
- `POST /jobs` quota is correct **serially** (`201,201,201,429,429`).
- `POST /profile` stores a 10-ASCII-character name intact; unknown GET/POST paths return `404 {"error":"no_route"}`.
- Unsupported methods (PUT/DELETE/OPTIONS/HEAD) return `501` (stdlib default) rather than being mishandled.
- Expected-to-break-but-didn't: `/invoices/abc` does **not** 500 (the id is passed as a bound parameter, so the non-integer is handled); `/items` `limit` is `int()`-cast so it is not itself an injection vector (only `sort` is).

## Not tested

- **Bob/user-2 account under concurrency and for its own quota** — the shared parallel run changed user 2's `id` via F2, so `/jobs` and `/me` 500 for that token for the rest of the run. Cross-user *reads* were still tested (F1 uses Bob's invoice as the target). Not re-tested on a clean instance.
- **Destructive write paths** — not exercised as proofs by policy; F1/F3/F4 are proven by reads, F2/F7 by writes to the caller's own row only.
- **Cloud metadata SSRF payoff** (`169.254.169.254`) — the request is *made* (proving no allow-list) but this host has no metadata service, so no secret was retrieved; not pursued further by policy (stop at proof).
- **Full SQLi data exfiltration** — injection is proven (F3) via one error-based and one blind read; extraction was not carried further, by policy.
- **Browser matrix / responsive / dark-mode / a11y depth** — the UI was tested in one engine (the session's built-in browser): render, console, and the search-form target. Dark mode (a `prefers-color-scheme` block exists at `app.py:30`), mobile breakpoints, keyboard and screen-reader behaviour were not exercised — the page's script is broken (F11) and its form is broken (F12), which were the higher-value UI findings.
- **HTTPS / HSTS / certificate / CORS / cookies** — the service is plain HTTP by design and uses no cookies, so transport-TLS and cookie-flag checks do not apply. CORS is not set (no credentialed cross-origin surface).
- **File upload / SVG / archive handling, webhooks, scheduled jobs, queue consumers** — none exist in this product (`POST /jobs` increments a counter with no downstream worker). Marked not applicable.
- **Dependency audit / secrets in VCS history** — the fixture is a single file with no manifest and no repository history; nothing to audit.

## Suite added

| Location | Covers | Run with |
|---|---|---|
| `test_ledger.py` | F1–F14 as failing regression guards; health, serial quota, unauth 401 as passing guards | `LEDGER_URL=http://127.0.0.1:8910 python3 -m unittest test_ledger -v` |

14 finding-tests **fail today** (the regression guards; they flip to pass as each
fix lands); 3 sanity tests pass. Run captured at `evidence/F-suite-run.txt`.
Stdlib only — no install needed. The concurrency tests (F7/F8) are inherently
timing-sensitive; they were red 3/3 here but treat a single green as a flake, not
a fix.

## Evidence

`/path/to/workspace/eval/with_skill/`
— `report.md`, `surfaces.md`, `plan.md`, `test_ledger.py`, `evidence/` (raw
captures + one UI screenshot), `load/` (loadtest JSON). No live secrets or
personal data are stored; captured bodies contain only fixture seed data
(the "CONFIDENTIAL" note is fixture content, demonstrating F1 — not a real secret).
The `file://` proof deliberately read the fixture's own README, not a system file.
