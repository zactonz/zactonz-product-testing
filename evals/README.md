# Evaluation set

Material for measuring whether the skill actually works, rather than judging it by
reading it. Results of the last run are in `RESULTS.md`.

## Contents

| Path | What it is |
|---|---|
| `fixture/app.py` | A deliberately defective API with ten planted defects across all four dimensions. Python standard library only; binds to `127.0.0.1` exclusively |
| `fixture/README.md` | The contract the fixture claims to honour — the oracle the test pass is scored against |
| `fixture/GROUND-TRUTH.md` | The answer key. A test run must not read this |
| `grade.py` | Scores a run's recall. Requires a defect's surface *and* mechanism to co-occur before counting a hit |
| `runs/<date>/` | Saved runs, one directory per arm |
| `RESULTS.md` | The written comparison |

## A caution about the fixture

`fixture/app.py` is insecure on purpose: it contains a missing authorization
check, SQL injection, reflected XSS, server-side request forgery, debug-mode
stack traces and a non-atomic quota. It exists to be found out.

Run it on a loopback interface only, never on a shared or reachable host, and stop
it when you are done. It keeps all state in memory, so a restart resets it — which
is also how you get a clean instance between runs.

## A note on the saved runs

The run artifacts under `runs/` are verbatim except for two redactions, made
before publication and listed here so nothing looks edited without explanation:

- Absolute paths from the machine the runs happened on were replaced with
  `/path/to/workspace` and `/Users/engineer`.
- The unaided run proved the file-read flaw by reading the host's `/etc/passwd`,
  and a fragment of it reached that report. The captured contents were replaced
  with `[redacted: the file's contents were returned verbatim]`. The finding is
  unchanged; the host's account records were not ours to publish.

The skill-guided run needed no content redaction: it proved the same flaw against
the fixture's own README rather than a system file, which is the rule in
`references/security.md` doing its job.

## Re-running

```bash
# 1. Start the fixture.
cd fixture && python3 app.py 8910

# 2. In a second shell, run both arms against it. Give each agent the same prompt
#    and the same authorization; point only one of them at the skill. Keep them
#    sequential — a shared instance lets one run's writes contaminate the other,
#    which happened on 7 Oct 2026 and is noted in RESULTS.md.
#    Save each arm to runs/<date>/with_skill/ and runs/<date>/without_skill/.

# 3. Score.
python3 grade.py runs/<date>
```

Restart the fixture between arms so each starts from the same state.

## When to re-run this

Any change to `SKILL.md` or to a reference file that is meant to change what the
skill finds, how it reports, or what it refuses to do. Reading a revision and
judging it plausible is exactly the failure the skill itself is written against.

If you extend the fixture with new defects, verify each one reproduces before
adding it to the answer key, and add a matching entry to `grade.py` — a defect
with no scoring rule is invisible to the measurement.
