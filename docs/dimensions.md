# The four dimensions

Testing splits into four dimensions. Ask for one, several, or none — naming none
runs all four. Each has a reference file the skill loads only when it reaches that
dimension, so asking for one does not pay for the others.

## Scoping a run

Name them directly, or describe what you want and let the wording select:

| You say | Dimensions selected |
|---|---|
| "find the edge cases in the invoice form" | functionality |
| "does the dashboard still work?" | ui |
| "can it handle Black Friday?" | load |
| "is this upload handler safe?" | security |
| "full QA pass before release" | all four |
| "load and security against staging" | load, security |

If a dimension has no surface in your product, the skill says so in the report's
**Not tested** section with the reason and skips it. A pure library has no UI; a
static brochure site has no authorization boundary. That is useful information
rather than a gap — what you do not want is a dimension silently dropped, which is
why it is written down either way.

## Functionality

The dimension that finds the most defects in working software, because its subject
is the gap between what a surface promises and what it does.

- **Boundary and malformed input** across roughly eighty input classes — absence
  and emptiness, numeric edges and overflow, string limits and whitespace, Unicode
  that breaks naive truncation and uniqueness checks, wrong types and shapes,
  identifiers that do not exist or belong to someone else, date and timezone edges,
  file and encoding cases. The discipline is working through the catalogue per
  input rather than relying on the three cases that come to mind, because those are
  the ones already handled.
- **State and sequence** — the empty state, the single-item state, the large state,
  replayed submits, out-of-order operations, and interrupted writes, where the
  question is what got left behind.
- **The authorization matrix**, built as an explicit grid of callers against
  surfaces, so the missing cells are visible rather than implied.
- **Concurrency and idempotency** — simultaneous creates against a unique key, lost
  updates, counter and quota races, and retries of requests whose response was lost.
- **The error contract** — right status code, actionable message, nothing leaked,
  consistent shape, and nothing half-applied after a failure.

It also insists on an oracle: a documented contract, a schema, consistency with
the product's own siblings, or a labelled judgement call. A finding with no basis
for calling the behaviour wrong is reported as an unspecified behaviour, which is
honest and still useful.

## UI

Verifies what a person sees and can do in a real browser, rather than what the
markup suggests they would.

- **Rendering** — no blank page, no error overlay, no leaked template syntax, no
  visible `undefined` or `NaN`, and the real content present rather than just the
  shell
- **Every state** — loading, empty, error and populated. The empty state is the
  most-skipped screen in software and the first one a new user sees
- **Interaction** — primary actions and their consequences, double-clicked submits,
  clicking during an in-flight request, keyboard-only operation, and focus
  behaviour around modals
- **Forms** — empty submit, each field invalid in turn, paste and autofill rather
  than typing, and whether a failed submit preserves what was typed
- **Responsive and theme** — 375px, 768px and desktop; light and dark, including
  the system preference rather than only an in-page toggle
- **Accessibility** — automated scanning where a scanner is available, plus the
  things no scanner judges: contrast, focus visibility, alt text that conveys
  meaning, heading structure, real labels rather than placeholders, and whether
  dynamic content is announced
- **Console and network** — uncaught exceptions on pages that look correct, 4xx and
  5xx including assets, and anything sensitive in a URL

It reads pages as text to assert, and screenshots for proof — cheaper and more
precise for anything textual, with images reserved for what only an image settles.

## Load

Finds the point where the product stops meeting its promise under pressure, and
characterises what happens past it. Every product has such a point; the question
is whether you found it or a customer did.

Four shapes, named separately because they answer different questions:

| Shape | Question |
|---|---|
| **Load** | Does it hold up under the traffic it is built for? |
| **Stress** | Where is the ceiling, and what breaks first? |
| **Soak** | Does it leak? Memory, descriptors, pool exhaustion — invisible in a minute |
| **Spike** | Does it survive the transient, and does it *recover*? |

Method that matters: a single-worker baseline first, one variable at a time, warmup
discarded, long enough for garbage collection and cache expiry to appear, and the
environment recorded alongside every number so a laptop figure is not later quoted
as production capacity.

Results are reported as percentiles, never as a mean — a 50ms mean routinely hides
2% of requests at eight seconds, and that tail is what users complain about.
Throughput and latency are reported together, because high throughput at a
twelve-second p99 is a queue filling up rather than capacity.

The most valuable half is past the ceiling: whether it sheds load or collapses,
whether it recovers unaided when traffic stops, whether it survives a dependency
failing and reconnects without intervention, and whether anything is corrupted
afterwards. Data damage under load outranks every latency number in the report.

Rate limits and quotas are tested as part of the contract — the threshold, a
parseable 429 rather than a hang, correct retry headers, the right subject, and
whether concurrent requests can straddle the boundary.

## Security

Verifies that the product's own protections hold. It thinks in controls rather than
exploits: for each control the product relies on, what is the minimum request that
shows whether it is present?

- **Authorization**, tested first and everywhere, because the check is written per
  handler and therefore forgotten per handler. Two accounts, and for every surface
  taking an identifier: can one read, update or list the other's data; can a
  privileged field be set on your own record; are the surfaces with no caller in the
  repo protected
- **Authentication and sessions** — credential verification, user enumeration,
  token rejection when expired or tampered, whether logout invalidates server-side,
  reset token scope and reuse, cookie flags
- **Injection boundaries** — one probe per context to establish whether input can
  become syntax: SQL, HTML, shell arguments, templates, paths, XML entities,
  deserialization, log and header injection
- **Requests the server makes for you** — any surface taking a URL, checked against
  loopback, link-local and private ranges, non-HTTP schemes, hostnames resolving
  inward, and redirects from public to private, which is where most implementations
  fail
- **Secret leakage** — responses, error pages, headers, the client bundle, publicly
  reachable config and backup paths, repository history, and logs
- **File handling, transport headers, configuration and dependencies**
- **Abuse and cost** — cheap requests triggering expensive operations, which is a
  direct route to a large bill

It stops at proof and does not pivot. Once a control is shown to be missing, the
finding is complete; reading one record demonstrates the flaw, and enumerating the
table adds no information while turning a test into a breach. See
[Safety model](safety.md).

This verifies controls. It does not model a determined attacker, and where that
matters it is not a substitute for a scoped engagement.
