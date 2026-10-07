# Writing the report

Read this before writing the report. The report is the only part of a test pass
anybody reads, and it is where the work is usually wasted: a real defect buried at
position fourteen of an unranked list gets skimmed past and shipped.

## Contents

- [The reader and the decision](#the-reader-and-the-decision)
- [Severity](#severity)
- [Anatomy of a finding](#anatomy-of-a-finding)
- [Findings that get fixed](#findings-that-get-fixed)
- [The verdict](#the-verdict)
- [Not tested](#not-tested)
- [When nothing broke](#when-nothing-broke)
- [Evidence on disk](#evidence-on-disk)

## The reader and the decision

Someone is deciding whether to ship. They will read the verdict and the first
three findings, and they will skim the rest. Write for that: lead with the
decision, rank ruthlessly, and put the detail below where it can be found when
somebody starts fixing.

Two numbers determine whether the report is trusted later: how many findings turn
out to be real, and whether the coverage boundary was stated honestly. Both are
hurt by padding. A report with four real findings beats one with four real
findings and eleven speculative ones, because the eleven cost the reader time and
teach them to discount the four.

## Severity

Judge on impact and reachability, not on how alarming the defect's name is. A
theoretical flaw in an unreachable code path is Low; a boring missing check on the
main account page is Critical.

**Critical** — data loss or corruption; any authentication or authorization bypass;
secret exposure; the product unusable for everyone; money moved or charged
incorrectly. Reachable by an ordinary user or an unauthenticated caller. *Do not
ship.*

**High** — a core promise broken for many users with no workaround; a crash on
ordinary input; a security flaw needing unusual-but-attainable conditions; silent
failure of something the user believes succeeded. *Fix before shipping.*

**Medium** — real breakage that is narrow, recoverable or has a workaround; a
broken edge case a minority will hit; degradation under load that is above expected
traffic; a missing hardening measure with no current exploit path. *Schedule.*

**Low** — cosmetic; a confusing message; a latent problem with no present impact;
an inconsistency with no user-visible consequence. *Backlog.*

Two adjustments worth making deliberately:

- **Silent wrongness beats loud failure.** A crash is noticed and fixed; a wrong
  number, a dropped record or a half-saved form propagates for months. Rate silent
  incorrectness a level above a visible failure of similar scope.
- **Reachability cuts both ways.** Behind an admin-only surface, drop a level.
  Reachable unauthenticated, raise one.

If you are between two levels, pick the lower one and say in a sentence why it
could be argued higher. That is more useful than inflating it, and it keeps the
severity scale meaning something across reports.

## Anatomy of a finding

Each finding, in this order, because this is the order the reader needs it:

```markdown
### F3 · High · POST /v1/export accepts a negative `limit` and returns the whole table

**Surface** `POST /v1/export` — `src/Http/ExportController.php:88`

**Reproduction**
```bash
curl -sS -X POST http://127.0.0.1:8082/v1/export \
  -H 'Content-Type: application/json' \
  -d '{"limit": -1}'
```

**Observed** 200, with 48,201 rows — every row in the table, ignoring the caller's
account scope. Reproduced 3/3.

**Expected** 400 with `{"error":{"code":"invalid_limit"}}`, per `docs/api.md:112`,
which documents `limit` as 1–1000.

**Why it matters** `limit` is passed to the query without validation, so a
negative value removes the `LIMIT` clause. Any caller can dump the full table in
one request — a data exposure and an availability problem at once.

**Evidence** `evidence/F3-negative-limit.txt`

**Fix** Validate `limit` as an integer in 1–1000 before it reaches the query
builder, at `ExportController.php:88`, and add the account scope to the query.
```

Four properties make this work: the title states the defect so the index is
readable on its own; the reproduction is copy-pasteable and minimal; observed and
expected are separated with a cited source for the expectation; and the fix names a
location rather than offering advice.

## Findings that get fixed

**Minimise the reproduction before you write it.** Strip the input to the smallest
thing that still fails. A one-line reproduction gets fixed this afternoon; a
40-line one gets deferred and then forgotten.

**Cite the expectation.** "Should return 400" invites argument. "`docs/api.md:112`
documents `limit` as 1–1000" ends it. When there is no documented expectation, say
so and label the finding a judgement call — the user can then overrule you in
seconds instead of investigating.

**State the count for anything intermittent.** "Reproduced 3/3" and "reproduced
1/10" lead to different decisions, and a finding with no count is assumed to be
1/1 and unreliable.

**One defect per finding.** Two bugs in one entry means one gets fixed and the
other silently closes with it.

**Separate symptom from cause**, and do not guess at the cause with confidence you
do not have. "Returns 500; the log shows a null dereference at `Foo.php:40`" is
evidence. "Returns 500, probably a race condition" is a guess that will send
somebody down the wrong path for a day — mark it as a hypothesis or leave it out.

**Report the near-miss.** A control that happens to be unreachable today, a
validation that works only because of a coincidence upstream, a test that passes
for the wrong reason — these are worth a Low finding, because the next refactor
removes the coincidence.

## The verdict

Three sentences at the top, before anything else: what you tested, what you found,
and whether you would ship it. Commit to a recommendation. "Several issues were
identified" is not a verdict; "Do not ship: one authorization bypass on the
invoices endpoint lets any user read any account's data" is.

Then the counts by severity, so the scale of the work is visible immediately.

## Not tested

Keep this section as you work, not at the end, and let it be as long as it needs
to be. For each gap: what, and why — no environment, no credentials, needs
production data, out of scope, ran out of the agreed window, blocked by an earlier
failure.

This is the section that makes the rest of the report trustworthy. A reader who
can see the boundary knows what the silence elsewhere means. A reader who cannot
will assume total coverage, and that assumption is what the report will be blamed
for later.

Explicitly list the dimensions you skipped and why — including the ones that do
not apply, since "no UI surface; this is a library" is useful information.

## When nothing broke

Say so plainly, and make the pass legible rather than reassuring. "No defects
found" is only worth anything alongside what was attempted:

- the surfaces exercised, from the inventory, with the count tested over the count
  found
- the case classes run — which rows of the input catalogue, which authorization
  cells, which load levels
- what you expected to break and did not, which is the most informative thing in a
  clean report
- the coverage boundary, in the same detail as any other report

A clean report with no visible attempt is indistinguishable from no testing at all,
and will be treated as such the first time something breaks in production.

## Evidence on disk

Beside `report.md`:

```
test-reports/2026-10-07-full/
├── report.md
├── surfaces.md              inventory from step 2
├── plan.md                  the case table
├── evidence/
│   ├── F1-authz-bypass.txt  request, response, headers
│   ├── F3-negative-limit.txt
│   └── F5-mobile-overflow.png
└── load/
    ├── baseline.json
    └── stress-100.json
```

Name evidence files for the finding they support, so a reader following a
reference can find it without searching. Keep raw output verbatim — trimmed output
is reinterpreted output.

Two things to check before finishing: that no captured payload or screenshot
carries real personal data or a live secret, and that the user knows the directory
exists. Offer to gitignore it if it is bulky, and ask before committing anything
containing captured data.
