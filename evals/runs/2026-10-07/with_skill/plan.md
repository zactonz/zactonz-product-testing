# Test plan — Ledger API

Target: `http://127.0.0.1:8910` (local throwaway fixture, user-owned, full
authorization for all four dimensions including load and security). Tokens:
`tok-alice` = user 1, `tok-bob` = user 2.

Ordered by blast radius x likelihood. Oracle for each is the README promise table
unless noted.

| # | Surface | Promise | Cases | Dimension |
|---|---|---|---|---|
| P1 | `GET /invoices/<id>` | caller's own invoice; 404 for anyone else's | alice reads 101 (own), alice reads 102 (bob's), bob reads 101, unauth, non-int id, missing id | functionality, security |
| P2 | `PATCH /me` | updates only own `name` | set `name`; set `is_admin`; set `id`; set `jobs_used`; field-name injection; unknown field | security, functionality |
| P3 | `GET /preview?url=` | fetches a public URL, returns snippet | public http, `file://` local read, loopback `127.0.0.1`, link-local `169.254.169.254`, bad url (500), missing url | security |
| P4 | `GET /items?limit=&sort=` | own items; limit 1–100 def 20; sort in {id,label,price} | limit 0/-1/1/100/101/1000/abc; sort id/label/price/note(bad)/injection marker/boolean-blind/cross-table | functionality, security |
| P5 | `GET /search?q=` | HTML results page | reflected `<script>` / `<zxss>` marker, attribute break, empty | security |
| P6 | `POST /jobs` | max 3 per user; 4th → 429 | serial 1..4 (quota), concurrent 20 vs quota 3 (race), unauth | functionality, load, security |
| P7 | `POST /profile` | display name max 10 characters | 10 ASCII, 11 ASCII, 10 multibyte chars, emoji, empty, missing, non-string | functionality |
| P8 | `who()` auth | Bearer token → user | no `Bearer ` prefix, duplicated `Bearer `, empty, wrong token | security |
| P9 | 500 error contract | no stack/SQL/path leak | provoke 500 via limit=abc, sort=badcol, preview bad url; inspect body | security, functionality |
| P10 | `GET /app` | the web UI | renders, console errors, `window.ledgerInit` defined, dark mode, mobile | ui |
| P11 | Methods/routes | 404 no_route | PUT/DELETE/HEAD/OPTIONS, unknown path | functionality |
| P12 | `GET /health` | `{"ok":true}` | happy + load baseline | functionality, load |

Not applicable up front: file upload (no upload surface), SVG/archive handling,
HTTPS/HSTS/cert (plain HTTP by design, local), git history secrets (fixture is one
file). These go in Not tested with reasons.
