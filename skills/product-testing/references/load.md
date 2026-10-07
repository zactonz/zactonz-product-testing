# Load, stress and resilience

Read this when running the `load` dimension. The goal is to find the point where
the product stops meeting its promise under pressure, and to characterise how it
behaves past that point — because every product has such a point, and the only
question is whether you found it or a customer did.

## Contents

- [Before generating any traffic](#before-generating-any-traffic)
- [Pick a generator](#pick-a-generator)
- [Driving the bundled generator](#driving-the-bundled-generator)
- [Four shapes of test](#four-shapes-of-test)
- [Method](#method)
- [Reading the numbers](#reading-the-numbers)
- [Finding the bottleneck](#finding-the-bottleneck)
- [Rate limits and quotas](#rate-limits-and-quotas)
- [Resilience past the limit](#resilience-past-the-limit)
- [Reporting load results](#reporting-load-results)

## Before generating any traffic

A load test and a denial-of-service attempt are the same packets. Three rules
make the difference, and they are not paperwork:

1. **Target something the user controls.** Local or staging by default. Never a
   third party, and never a shared service, without the owner's authorization.
2. **Get an explicit ceiling for anything live.** If the user wants production
   tested, agree the concurrency, the duration and the window first, then hold to
   them. A test that takes the product down costs more than it discovered.
3. **Watch what you are pointing at.** Hitting an endpoint that sends email,
   charges a card, calls a metered third-party API or writes rows forever will
   produce a bill, a mailbox full of real messages, or an unusable database. Check
   the handler's side effects before the first run, and prefer a read-only
   endpoint for calibration.

The bundled generator refuses non-local hosts unless `--allow-remote` is passed,
so that the decision to point load at something remote is deliberate rather than
a typo.

## Pick a generator

```bash
for t in k6 wrk hey vegeta oha ab siege; do printf '%-10s' "$t"; command -v $t >/dev/null && echo present || echo absent; done
```

| Available | Use |
|---|---|
| `k6` | Best option when present: scenarios, thresholds, stages, scriptable checks, and a result format the user can keep |
| `wrk`, `oha`, `hey`, `vegeta` | Fine for single-endpoint throughput and latency |
| Nothing, or `ab` only | `scripts/loadtest.py`. Prefer it over `ab`, which reports no percentiles beyond a coarse table, mishandles keep-alive by default, and cannot drive a multi-step flow |

Do not install a load tool without asking. The bundled generator needs only
Python 3 and is enough for everything in this file.

## Driving the bundled generator

```bash
python3 <skill>/scripts/loadtest.py --help
```

A baseline, then a load step, then a stress ramp:

```bash
# Baseline: one worker, serial. This is the floor; everything later is compared to it.
python3 loadtest.py http://127.0.0.1:8080/health -c 1 -n 50 --json base.json

# Load: expected peak concurrency, sustained.
python3 loadtest.py http://127.0.0.1:8080/v1/thing -c 25 -d 60 \
  -X POST -H 'Content-Type: application/json' -b @payload.json \
  --expect-status 200,201 --json load-25.json

# Stress: climb until something gives.
for c in 10 25 50 100 200; do
  python3 loadtest.py http://127.0.0.1:8080/v1/thing -c $c -d 30 --json "stress-$c.json"
done
```

Useful flags: `--rps` caps arrival rate independently of concurrency, which is how
you reproduce real traffic rather than a closed loop of workers; `--ramp` climbs to
full concurrency gradually instead of hitting cold caches with a wall; `--think`
inserts a pause between a worker's requests, which models users rather than bots;
`--csv` writes per-request records when you want to plot the tail yourself.

## Four shapes of test

They answer different questions, and the words are often used interchangeably by
mistake. Say which one you ran.

- **Load** — expected peak traffic, sustained for minutes. Question: does it meet
  its promise under the traffic it is built for?
- **Stress** — climb past that until it degrades. Question: where is the ceiling,
  and what breaks first?
- **Soak** — moderate traffic for a long time, an hour or more. Question: does it
  leak? Memory growth, file descriptors, connection pool exhaustion and disk fill
  are invisible in a 60-second run and are what takes services down on day three.
- **Spike** — from idle to very high and back, abruptly. Question: does it survive
  the transient, and does it *recover* — which is the part usually left untested.

## Method

**Baseline first, with one worker.** Without it you cannot say whether 300ms under
load is degradation or just what this endpoint costs.

**Change one variable at a time.** Raising concurrency and payload size together
produces a number you cannot attribute to either.

**Let it warm up, then measure.** The first requests pay for JIT, connection
setup, cold caches and lazy initialisation. Either discard the opening seconds or
use `--ramp`, and say which you did.

**Run long enough to be real.** Ten seconds measures a burst. Garbage collection
pauses, cache expiry and connection recycling need minutes to show up.

**Repeat the interesting runs.** Three runs at the concurrency that mattered, and
report the spread. A single run on a laptop also running a browser and a compiler
is not a measurement.

**Record the environment with the numbers.** Machine, CPU count, whether the
database is local, whether anything else was running, and whether this is a debug
build. Load numbers without that context get quoted later as if they were
production capacity, and they are not.

**Find the knee, not just a pass.** Plot throughput against concurrency. It climbs
roughly linearly, flattens, and often falls. The flattening point is the real
capacity; past it, latency rises while throughput does not, and anything beyond
the fall is a queue the product cannot drain.

## Reading the numbers

**Means lie; percentiles do not.** A 50ms mean can hide 2% of requests at eight
seconds. Report p50, p95 and p99, and the max. If p99 is many multiples of p50,
something is intermittent — garbage collection, a lock, a cache miss path, a
connection pool wait — and that tail is what users actually complain about.

**Throughput and latency together, never apart.** 2,000 requests per second at a
12-second p99 is not throughput, it is a queue filling up.

**Errors are a result, not a failed run.** The error mix at each level is the
finding. Distinguish:

- **Connection refused / reset** — the listener's accept queue is full, or the
  process died. Check whether it is still running afterwards; a crash is the
  finding.
- **Timeout** — work is queued behind something saturated. Nothing is broken yet,
  but the client has already given up, so the user experienced an outage.
- **5xx** — the product itself failed. Read its logs for the cause; this is the
  most actionable class.
- **429 with a sane body** — working as designed, which is a pass, not a failure.
  Reclassify these before reporting; a run that is 90% 429 against a documented
  rate limit is a successful test of the rate limiter.

**Watch the server, not only the client.** During the run, keep an eye on process
CPU and memory, the error log, connection counts, and the database's slow query
log. Client-side numbers tell you that it got slow; the server tells you why.

## Finding the bottleneck

When throughput flattens, the usual causes, roughly in order of how often they
turn out to be it:

- **A database query without an index**, or one executed per row inside a loop.
  Check the slow query log and the query count per request; an endpoint issuing 400
  queries will not scale however much hardware it gets.
- **A connection pool smaller than the concurrency.** Latency rises in clean steps
  as requests wait their turn — a very recognisable signature.
- **A synchronous call to something external** — a third-party API, an email
  send, an image conversion — inside the request path, which caps you at that
  dependency's latency.
- **A lock, or a single-threaded section**, where CPU sits at one core's worth
  however much concurrency arrives.
- **Process or worker count** — PHP-FPM `pm.max_children`, a thread pool, a single
  process. Concurrency above that number simply queues.
- **Per-request allocation** proportional to payload size, where memory climbs
  with concurrency until the process is killed.

Name the bottleneck in the report when you can identify it. "Flattens at 40 req/s
because each request runs 1 + N queries against an unindexed column" is a fix;
"slow under load" is not.

## Rate limits and quotas

If the product has limits, they are part of the contract and belong in this
dimension:

- The limit triggers at the documented threshold, not at half or double it
- The response is 429 with a parseable body, not a 500 or a hang
- `Retry-After` or the remaining-quota headers are present and correct
- Waiting the stated interval genuinely restores service
- The limit is per the right subject — per key, per account, per IP — and one
  account's traffic cannot exhaust another's allowance
- Concurrent requests cannot straddle the boundary: fire N at once against a quota
  of 1 and verify exactly one succeeded. A quota implemented as read-then-write
  without atomicity fails exactly here, and it is both a correctness bug and a
  billing one
- Exhausting a quota degrades cleanly rather than corrupting the counter

## Resilience past the limit

The most valuable half of this dimension is what happens at and beyond the
ceiling, because that is the state the product will be in during an incident:

- **Does it shed load or collapse?** Returning 503 quickly to some requests is
  healthy. Accepting everything and timing out all of it is collapse, and it takes
  longer to recover from.
- **Does it recover unaided?** Stop the traffic and check that it returns to
  baseline latency within seconds. A product that stays degraded after the spike
  passes needs a restart during every incident.
- **Does it survive its dependencies failing?** Stop the database or the cache
  mid-run and watch. A clear 503 is right; a hang until timeout, a crash, or a
  stack trace to the client is not. Restart the dependency and confirm it
  reconnects without intervention — missing reconnect logic is a very common and
  very expensive finding.
- **Are timeouts bounded everywhere?** An unbounded outbound call means one slow
  dependency consumes every worker.
- **Is anything corrupted afterwards?** Check for half-written records, orphaned
  rows, stuck jobs and wrong counters once the dust settles. Data damage under load
  outranks every latency number in the report.

## Reporting load results

Give a table, not prose:

| Scenario | Conc | Dur | Req/s | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|---|---|
| Baseline | 1 | 50 req | 24.1 | 41ms | 48ms | 52ms | 0 |
| Load | 25 | 60s | 212 | 108ms | 390ms | 720ms | 0 |
| Stress | 100 | 30s | 228 | 410ms | 2.9s | 9.8s | 31 timeouts |

Then state the capacity in one sentence a non-specialist can act on — "holds
~210 requests per second with p95 under 400ms; past roughly 50 concurrent the
connection pool saturates and latency climbs while throughput does not" — and
record the environment the numbers came from.
