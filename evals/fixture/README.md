# Ledger API

A small invoicing service. Two users exist, authenticated by bearer token:
`tok-alice` (user 1) and `tok-bob` (user 2).

## Run

    python3 app.py 8910

## Endpoints

| Method | Path | Auth | Promise |
|---|---|---|---|
| GET | `/health` | none | `{"ok":true}` |
| GET | `/app` | none | the web UI |
| GET | `/search?q=` | none | HTML results page |
| GET | `/invoices/<id>` | token | the caller's own invoice; 404 for anyone else's |
| GET | `/items?limit=&sort=` | token | the caller's own items. `limit` is 1–100, default 20. `sort` is one of `id`, `label`, `price` |
| GET | `/preview?url=` | none | fetches a public URL and returns a snippet |
| POST | `/jobs` | token | queues a job. Each user may queue at most 3; the 4th returns 429 |
| POST | `/profile` | token | sets the display name, max 10 characters |
| PATCH | `/me` | token | updates the caller's own `name`. No other field is user-editable |
