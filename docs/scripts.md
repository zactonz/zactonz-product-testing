# Bundled scripts

Two tools ship with the skill. Both use only the Python 3 standard library, so
there is no install step, and both are useful on their own — in CI, or from a
terminal, without Claude involved.

They live at `skills/product-testing/scripts/`, or
`~/.claude/skills/product-testing/scripts/` once installed.

## surfaces.py — surface inventory

Greps a pattern library across common web, API, CLI and job frameworks and groups
what it finds, so a test pass starts from what the product exposes rather than from
whatever a code skim surfaced.

```bash
python3 surfaces.py [root] [--out PATH] [--json] [--limit N]
```

| Option | Effect |
|---|---|
| `root` | Project root. Defaults to the current directory |
| `--out PATH` | Write the report to a file as well as stdout |
| `--json` | Emit JSON instead of Markdown |
| `--limit N` | Rows shown per category, default 40. Totals are always reported in full |

### What it reports

The detected stack, any test harness already present, file-based routes, and then
one section per category: HTTP routes and request entry points, API
specifications, pages and views, CLI entry points, scheduled jobs and queues,
webhooks and event handlers, authorization boundaries, outbound requests,
file-upload handling, raw SQL, and possible hardcoded secrets.

The harness detection is worth reading first — a suite written in a second style is
a suite nobody runs, so it tells you what idiom to match.

### Reading it honestly

It is a pattern scan, so it misses dynamically registered routes and anything
behind indirection, and it over-reports in a few categories by design. Three
sections need triage rather than being taken at face value:

- **Authorization boundaries** lists checks that *exist*. The finding is the
  surfaces with none, which you get by comparing against the route list.
- **Outbound requests** lists every HTTP client call. Only the ones whose URL comes
  from request input are candidates for server-side request forgery.
- **Possible hardcoded secrets** will match fixtures and examples. Verify before
  reporting, and never copy a live value anywhere.

It skips the directories you would expect — `node_modules`, `vendor`, build output,
caches — along with hidden directories other than `.github`, and worktree copies,
which otherwise scan the whole repository twice.

```bash
# Typical first move on an unfamiliar codebase.
python3 surfaces.py . --out surfaces.md --limit 100
```

## loadtest.py — concurrent load generator

Exists because `k6`, `wrk`, `hey` and `vegeta` are usually not installed, and
ApacheBench reports no usable percentiles. Use `k6` instead where it is available;
this covers everywhere else.

```bash
python3 loadtest.py URL [options]
```

### Shaping the run

| Option | Effect |
|---|---|
| `-c, --concurrency N` | Concurrent workers, default 10 |
| `-n, --requests N` | Total requests to send |
| `-d, --duration SEC` | Sustain traffic for this long. Mutually exclusive with `-n` |
| `--rps N` | Cap total arrival rate, modelling real traffic rather than a closed loop of workers |
| `--ramp SEC` | Stagger worker start over this period, instead of hitting cold caches with a wall |
| `--think SEC` | Pause between a worker's requests, modelling users rather than bots |
| `--warmup SEC` | Discard results from the first N seconds, so JIT and connection setup do not pollute the numbers |

### The request

| Option | Effect |
|---|---|
| `-X, --method` | HTTP method, default GET |
| `-H, --header 'K: V'` | Repeatable |
| `-b, --body DATA` | Body, or `@path` to read from a file |
| `--timeout SEC` | Per-request timeout, default 10 |
| `--expect-status LIST` | Comma-separated codes to count as success. Default is anything under 400 |
| `--insecure` | Skip TLS verification |

### Output and gating

| Option | Effect |
|---|---|
| `--json PATH` | Full summary, including the per-second timeline |
| `--csv PATH` | Per-request records, for plotting the tail yourself |
| `--fail-over-errors PCT` | Exit 1 if the error rate exceeds this |
| `--fail-over-p95 MS` | Exit 1 if p95 exceeds this |
| `-q, --quiet` | Suppress progress output |

The two `--fail-over-*` flags make it a CI gate: it exits 1 on breach and names
what breached.

### The safety guard

Non-local targets are refused unless `--allow-remote` is passed, so aiming load at
a remote host is always a deliberate act rather than a typo. Local means loopback,
`127.0.0.0/8`, `::1`, or a name ending `.localhost` or `.test` — a private-range
address is still somebody's server and needs the flag.

Before passing it: a load test and a denial-of-service attempt are the same
packets. Only target hosts you own or are authorized to test, agree a ceiling
first, and check what the endpoint does before hitting it ten thousand times —
mail, payments and metered third-party calls all arrive as consequences.

### What it reports

Request and error counts, error rate, throughput, bytes received; latency as min,
mean, p50, p75, p90, p95, p99 and max; a status-code histogram; errors grouped by
class (`timeout`, `connection_refused`, `connection_reset`, `dns_failure`,
`tls_error`, `unexpected_status_<code>` and so on); and a per-second timeline of
requests, errors and p95.

Percentiles are the point. On a seeded tail during development it reported a p50 of
13ms against a p90 of 254ms, where the 60ms mean hid the tail completely.

A run that measured nothing, or in which nothing succeeded, prints a warning rather
than a page of zeros that could be mistaken for a pass.

### Worked sequence

```bash
# 1. Baseline. One worker, serial. Everything later is compared to this.
python3 loadtest.py http://127.0.0.1:8080/health -c 1 -n 50 --json base.json

# 2. Load. Expected peak concurrency, sustained, warmup discarded.
python3 loadtest.py http://127.0.0.1:8080/v1/thing -c 25 -d 60 --warmup 5 \
  -X POST -H 'Content-Type: application/json' -b @payload.json \
  --expect-status 200,201 --json load-25.json

# 3. Stress. Climb until something gives; the knee is the real capacity.
for c in 10 25 50 100 200; do
  python3 loadtest.py http://127.0.0.1:8080/v1/thing -c $c -d 30 --json "stress-$c.json"
done

# 4. As a CI gate.
python3 loadtest.py http://127.0.0.1:8080/v1/thing -c 20 -d 30 \
  --fail-over-errors 1 --fail-over-p95 500 -q
```

Record the environment with any number you keep — machine, CPU count, whether the
database is local, whether it is a debug build. Load figures get quoted later as
production capacity, and without that context they are not.
