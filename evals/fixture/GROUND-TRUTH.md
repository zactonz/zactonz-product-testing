# Planted defects (verified reproducing)

| ID | Severity | Surface | Defect |
|---|---|---|---|
| D1 | Critical | `GET /invoices/<id>` | No ownership check. Alice's token reads Bob's invoice 102. |
| D2 | Critical | `PATCH /me` | Mass assignment: any field in the body is written, so `{"is_admin":1}` escalates. |
| D3 | High | `GET /items?limit=-1` | Negative limit skips the LIMIT clause; returns all 30 rows instead of 20. |
| D4 | High | `GET /items?sort=` | `sort` interpolated into ORDER BY — SQL injection. Subqueries execute. |
| D5 | High | `GET /search?q=` | Reflected XSS; `q` echoed into HTML unescaped. |
| D6 | High | `GET /preview?url=` | SSRF; fetches any URL including loopback, no scheme or range filter. |
| D7 | Medium | all POST/PATCH | Malformed JSON returns 500 with a full stack trace (DEBUG=True) rather than 400. |
| D8 | High | `POST /jobs` | Quota read-then-write race: 10 concurrent requests allow 8 against a quota of 3. |
| D9 | Medium | `POST /profile` | Truncates to 10 *bytes*, splitting multibyte characters into a lone surrogate. |
| D10 | Low/Med | `GET /app` | UI: unlabelled input, `outline:none` on focus, `.panel` hardcoded white in dark mode, 420px table overflows 375px viewport, `window.ledgerInit` undefined → console TypeError. |

Also present and worth finding: `Server:` header leaks version, no rate limit on
`/jobs`, `/preview` and `/search` need no auth at all.
