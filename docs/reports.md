# Reading a report

Reports land at `test-reports/<date>-<scope>/report.md` by default, with the
evidence beside them. The template is in `assets/report-template.md`.

## Shape

```
Verdict                 three sentences and a severity table
Findings                ranked most severe first
Load results            a table, a capacity sentence, the environment
Verified working        what was exercised and held up
Not tested              what was not covered, and why
Suite added             where the tests went and how to run them
Evidence                where the raw captures are
```

Read the verdict and the first three findings. They are ordered so that stopping
there is a reasonable thing to do.

## The verdict commits

It names what was tested, what was found, and whether to ship. "Several issues were
identified" is not a verdict and the skill is written against producing one. Expect
something closer to: *do not ship — one authorization gap on the invoices endpoint
lets any user read any account's data.*

## A finding

Each one carries, in this order: the surface and its location in the code; a
minimal copy-pasteable reproduction; what was observed, with a reproduction count;
what was expected, with the source that says so; why it matters; the evidence file;
and the specific fix with a named location.

Two details to look for. **The cited expectation** — "the schema documents `limit`
as 1–1000" ends an argument that "should return 400" invites; where no documented
expectation exists, the finding is labelled a judgement call so you can overrule it
in seconds. And **the reproduction count** — "reproduced 3/3" and "reproduced 1/10"
lead to different decisions, and an intermittent failure is worth knowing about
precisely because it is the kind that wakes people up.

## Severity

Judged on impact and reachability, not on how alarming the defect's name is.

| Level | Means | Action |
|---|---|---|
| **Critical** | Data loss or corruption, an authentication or authorization bypass, secret exposure, the product unusable for everyone, or money moved incorrectly — reachable by an ordinary or unauthenticated caller | Do not ship |
| **High** | A core promise broken for many users with no workaround, a crash on ordinary input, or a silent failure of something the user believes succeeded | Fix before shipping |
| **Medium** | Real breakage that is narrow, recoverable, or has a workaround; degradation above expected traffic; missing hardening with no current exploit path | Schedule |
| **Low** | Cosmetic, a confusing message, or a latent problem with no present impact | Backlog |

Two deliberate adjustments. **Silent wrongness rates above loud failure** — a crash
gets noticed and fixed, while a wrong number or a half-saved form propagates for
months, so silent incorrectness sits a level higher than a visible failure of
similar scope. And **reachability cuts both ways** — behind an admin-only surface,
a level down; reachable unauthenticated, a level up.

Where a finding sits between two levels it takes the lower one and says why it
could be argued higher. That keeps the scale meaning something across reports.

## The section that matters most

**Not tested** is what makes the rest of the report trustworthy, and it is the first
thing to read if you are deciding how much weight to put on a clean result.

A reader who can see the boundary knows what the silence elsewhere means. A reader
who cannot will assume total coverage. Expect it to be long, to distinguish *not
applicable* ("no upload surface exists") from *not reached* ("one browser engine
only; keyboard and dark-mode depth not exercised"), and to record anything that
compromised the run — a contaminated environment, a missing credential, an agreed
window that ran out.

A report with four findings and an eight-entry not-tested list is more useful than
one with fifteen findings and no stated boundary.

## When nothing broke

"No defects found" is worth something only alongside what was attempted. A clean
report should still show the surfaces exercised as a count over the inventory, the
case classes run, and — the most informative line in it — what was expected to break
and did not. A clean report with no visible attempt is indistinguishable from no
testing, and should be treated that way.

## The three outcomes

Every case is a verified pass, a verified failure, or not tested. Reports lie almost
exclusively by collapsing the third into the first, letting an untested area read as
silence that the reader hears as fine.

Before handing over, the skill runs a checklist: every claimed pass corresponds to
captured output rather than to code it read; every finding was reproduced at least
twice; every reproduction was re-run from a clean state and still fails; the
not-tested list is complete; no secret values appear anywhere; the build and
environment are recorded; and anything uncertain is labelled uncertain rather than
smoothed over.

If you find a claim in a report you cannot trace to an evidence file, treat that as
a defect in the report and say so — the whole method depends on that being
checkable.
