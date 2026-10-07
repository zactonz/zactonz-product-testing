# Product Testing

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg) ![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg) ![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)

A skill for Claude Code that tests a product the way a QA engineer would: it
inventories every surface the product exposes, attacks them across four
dimensions, and leaves behind both a runnable test suite and a findings report in
which every claim is backed by captured output.

Documentation: [`docs/`](docs/) · [developers.zactonz.com/skills/product-testing](https://developers.zactonz.com/skills/product-testing/)

## Why

Asked to test something, the default behaviour is to exercise the happy path, see
nothing break, and report that it works. That is the one outcome that costs real
money, because the team ships on it.

This skill replaces that with a method. It starts from an enumeration of what the
product actually exposes rather than from whatever a code skim surfaced, it aims
each case at a named failure instead of at confirmation, and it reports three
outcomes — verified pass, verified failure, and not tested — so the boundary around
the work is visible instead of implied.

## The four dimensions

Ask for one, several, or none; naming none runs all four.

| Dimension | Covers |
|---|---|
| **Functionality** | Boundary and malformed input across ~80 input classes, state and sequence defects, the authorization matrix, concurrency races, idempotency, and the error contract |
| **UI** | Real browser rendering, interaction, forms, keyboard and focus, responsive and dark mode, WCAG accessibility, console and network errors, visual regression |
| **Load** | Baseline, load, stress, soak and spike shapes; latency percentiles rather than averages; bottleneck identification; rate-limit and quota behaviour; recovery and degradation past the ceiling |
| **Security** | Authorization and ownership checks, authentication and sessions, injection boundaries, SSRF on URL-taking surfaces, secret leakage, file handling, transport headers, abuse and cost |

## What you get back

- **A test suite** in the project's existing idiom and location, wired to one
  command, with a failing test for every confirmed finding — so the fix is verified
  when the test flips rather than by re-reading the diff.
- **A report** with a committed ship-or-wait verdict, findings ranked by severity,
  a minimal copy-pasteable reproduction for each, and an explicit list of what was
  not tested and why.
- **The evidence** the report rests on, saved alongside it.

## Safety

The skill is built to be run against real products, so it is explicit about what
it will not do. It will not point load or security traffic at a host without the
user's go-ahead for that specific target; it will not use a destructive action as
a proof of anything; it will not trigger a surface that emails, charges or
notifies real people without agreement; it will not copy a discovered secret into
a report or a commit; and it will not install tooling, rewrite source to make a
test pass, or bypass a commit hook on its own initiative.

It also treats everything the product under test emits — error messages, page
content, API responses, logs — as data rather than as instruction. Output that
tries to direct the tester is reported as a prompt-injection finding, not obeyed.

## Measured, not asserted

Against a fixture with ten planted defects across all four dimensions, tested by
two agents on the same prompt with the same authorization — one with the skill,
one without:

| | With skill | Baseline |
|---|---|---|
| Planted defects found | 10/10 | 9/10 |
| Files delivered | 25 | 3 |
| Runnable test suite | 17 tests, 13 red as regression guards | none |
| Raw evidence captures | 16 + screenshot | 2 |
| Explicit not-tested section | 8 entries with reasons | a shorter note |
| Cost | 1.8× tokens, 2.3× wall clock | — |

Recall is close; a capable tester finds most defects unaided. What the skill adds
is the inventory, the evidence, the load data, the durable suite, and a stated
coverage boundary — plus restraint: given identical unrestricted authorization, the
baseline rewrote another account's primary key as a proof and could not restore it,
while the skill wrote only to its own row and restored what it changed.

Method, full results and the cost breakdown: [docs/evaluation.md](docs/evaluation.md).

## Documentation

| Page | Read it for |
|---|---|
| [Getting started](docs/getting-started.md) | Install, verify, first run, what comes back |
| [The four dimensions](docs/dimensions.md) | What each covers and how to scope a run |
| [Safety model](docs/safety.md) | What it will and will not do to a running system |
| [Reading a report](docs/reports.md) | Report shape, severity rubric, what to check |
| [Bundled scripts](docs/scripts.md) | CLI reference for both tools |
| [How it was measured](docs/evaluation.md) | Evaluation method, results, cost |

## Install

As a plain skill — copying the folder is the whole operation:

```bash
git clone https://github.com/zactonz/zactonz-product-testing.git
cp -r zactonz-product-testing/skills/product-testing ~/.claude/skills/
```

Or as a Claude Code plugin, which needs the marketplace registered first:

```bash
claude plugin marketplace add zactonz/zactonz-product-testing
claude plugin install zactonz-product-testing@zactonz-product-testing
```

Use `./.claude/skills/` instead of `~/.claude/skills/` to scope it to one project.
Either way, start a new session afterwards so the skill is picked up.

## Use

Ask for what you want tested in the ordinary way — the skill triggers on its own:

```
test the export endpoint before I ship it
can the API handle Black Friday traffic?
find the edge cases in the invoice form
is this upload handler safe?
full QA pass on the dashboard
```

To scope it deliberately, name the dimensions: *run the load and security
dimensions against the staging API*.

## Bundled tools

Both are Python 3 standard library only, with no install step, and are useful on
their own:

```bash
# Inventory what a codebase exposes: routes, CLI entry points, pages, specs,
# scheduled work, auth checks, outbound calls, uploads, raw SQL, possible secrets.
# Also reports the detected stack and any test harness already present.
python3 skills/product-testing/scripts/surfaces.py . --out surfaces.md

# Load-test an endpoint with real percentiles, a status histogram and classified
# errors. Doubles as a CI gate via --fail-over-errors / --fail-over-p95.
python3 skills/product-testing/scripts/loadtest.py http://127.0.0.1:8080/health \
  -c 25 -d 60 --expect-status 200 --json load.json
```

`loadtest.py` refuses a non-local target unless `--allow-remote` is passed, so
aiming load at a remote host is always a deliberate act.

## Requirements

| Component | Needed for |
|---|---|
| Claude Code | the skill itself |
| Python 3.9+ | the two bundled scripts |
| A browser driver | the UI dimension — the session's own browser tools, or Playwright, Cypress or Puppeteer if already in the project |

Nothing else is required. A load generator such as `k6` is used if present and
not installed if absent.

## Licence

Apache-2.0. Copyright Zactonz Technologies.
