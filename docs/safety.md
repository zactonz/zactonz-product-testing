# Safety model

Testing means running untrusted things, reading untrusted output and generating
traffic against something real. This page says exactly what the skill will and will
not do, so you can decide what to point it at.

The rules below live in `SKILL.md` as a block the skill treats as non-negotiable by
anything it encounters mid-run — not by a comment in the code, a note in a README,
a line in a log, a page under test, or a stated deadline. Where something seems to
require breaking one, it stops and asks instead.

## Authorization is per target, and comes only from you

The default is an instance started locally, or one you named explicitly. Load or
security work against anything shared or live needs your go-ahead for that specific
host, in that conversation, before the first request — along with an agreed
concurrency ceiling and duration, which it then holds to.

Text found inside the product is data, not permission. A page saying "this is a
test environment", a README saying "feel free to hammer this", a staging banner —
none of these establish who owns the machine, and none are accepted as
authorization. Approval for one target does not carry to another.

If you say "test it" and the only thing running is production, it says so and
offers to stand up a local instance.

Two reasons this is strict rather than ceremonial. A load test and a
denial-of-service attempt are the same packets, and a successful one against your
own production takes your product down. And probing infrastructure you do not own
is an attack whatever the intent.

## Destructive actions are never used as proof

Deleting, overwriting, truncating or mass-writing real data demonstrates nothing a
read cannot. A missing authorization check is proven by reading one record; a write
path is proven with a record the test created itself. It does not drop tables,
flush caches, rotate keys or clear queues on a shared instance.

In the [evaluation](evaluation.md) this distinction showed up plainly: given
identical unrestricted authorization, the run without the skill rewrote another
account's primary key as a demonstration and could not restore it, while the run
with the skill wrote only to its own row and restored what it changed.

## Nothing real goes out

Before testing a surface it checks whether that surface sends email or SMS,
charges a card, calls a metered third-party API, posts publicly, or notifies users.
Those need a sandbox, a test mode, or your explicit agreement. A test run that
emails live customers cannot be taken back, and a load test against a metered
endpoint arrives as an invoice.

## It stops at proof

Once a control is shown to be missing, the finding is complete. It does not chase
the weakness deeper, pivot from one flaw to another, or widen the blast radius to
make the report more impressive. Escalation is your decision, not the tester's.

Concretely, from the evaluation: the injection finding was established with one
error-based and one blind read and not carried through to extraction; the
cloud-metadata probe was issued to prove no allow-list existed and then dropped;
the file-read flaw was proven by reading the fixture's own README rather than a
system file. Each is recorded in the report's **Not tested** section as stopped by
policy, so you can see the decision rather than guess at it.

## Product output is data, never instruction

A tester spends its time reading error messages, page content, API responses,
filenames and logs — and on a real product some of that is attacker-controlled by
design. If any of it asks the skill to run a command, fetch a URL, change a file or
disregard its instructions, that is reported as a prompt-injection finding, and a
notable one. It is never acted on.

This matters more than it first appears. A stored field that reaches an
administrator's screen is a channel into whatever reads that screen, and a tester
is a thing that reads that screen.

## Secrets are reported by location, never by value

If a probe surfaces a live credential, token or personal data, you are told
immediately so it can be rotated, and only its location is recorded. The value
never goes into the report, a screenshot, a fixture, a commit or a message.

Rotation rather than deletion is the advice, because a secret in repository history
is not removed by a later commit.

## It changes the project only as asked

Adding tests and writing a report is the job. Installing tooling, editing
configuration, rewriting source to make a test pass, committing, pushing, or
bypassing a commit hook is not — it asks first. Where a dependency is genuinely
required it says what and why and leaves the decision to you.

It will not install a browser or a load generator unannounced. It uses `k6` if
present and the bundled Python generator if not.

## It cleans up

Servers it started are stopped, accounts and records it created are removed, config
it touched is restored, and anything it could not clean up is stated plainly.

## What this does not cover

The skill's restraint is not a substitute for your own scoping. It will refuse an
obviously unauthorized target and ask about an ambiguous one, but it cannot know
that a host you named is shared with a customer, or that an endpoint you pointed it
at bills per call. Tell it what it cannot see.

And the security dimension verifies controls. It is not a penetration test, does
not model a determined adversary, and where that distinction matters it should not
be reported as one.
