# Test report — <product> <version-or-commit>

**Tested** <YYYY-MM-DD> · **Build** <commit / version> · **Environment** <local | staging | production, host, relevant versions>
**Dimensions** <functionality | ui | load | security>
**Harness** <runner, browser, load generator, with versions>

## Verdict

<Three sentences: what was tested, what was found, ship or do not ship. Commit to a
recommendation.>

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

## Findings

<Ranked most severe first. Drop this section's placeholder if there are none and say
so in the verdict.>

### F1 · <Critical/High/Medium/Low> · <what is broken, stated as a defect>

**Surface** <endpoint / page / command> — <file:line>

**Reproduction**

```bash
<smallest command or steps that fail>
```

**Observed** <what happened, verbatim where short. Reproduced N/N.>

**Expected** <what should happen, and the source that says so — doc, schema, sibling behaviour>

**Why it matters** <mechanism, and the concrete consequence for users or the business>

**Evidence** `evidence/<file>`

**Fix** <the specific change, at a named location>

## Load results

<Drop if the load dimension was not run.>

| Scenario | Conc | Duration | Req/s | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |

**Capacity** <one sentence a non-specialist can act on, plus the bottleneck if identified>
**Environment** <machine, CPU count, local vs remote dependencies, debug or release build>

## Verified working

<What was exercised and held up — grouped, not exhaustively enumerated. Include what
you expected to break and did not, since that is the most informative part of a
clean result.>

## Not tested

<What was not covered, and why, one line each. Include dimensions skipped and
dimensions that do not apply. This section is what makes the rest of the report
trustworthy, so let it be long.>

## Suite added

| Location | Covers | Run with |
|---|---|---|
|  |  |  |

<Note which tests fail today against open findings — those are the regression guards,
and they flip when the fix lands.>

## Evidence

`<path to the evidence directory>` — <say whether it contains captured payloads or
screenshots that should not be committed>
