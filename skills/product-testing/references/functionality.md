# Functionality and edge cases

Read this when running the `functionality` dimension. The goal is to find inputs,
states and sequences where the product's actual behaviour diverges from what it
promises.

## Contents

- [Deciding what the right answer is](#deciding-what-the-right-answer-is)
- [Deriving cases from a surface](#deriving-cases-from-a-surface)
- [The input catalogue](#the-input-catalogue)
- [State and sequence](#state-and-sequence)
- [The authorization matrix](#the-authorization-matrix)
- [Concurrency and idempotency](#concurrency-and-idempotency)
- [The error contract](#the-error-contract)
- [Fixtures and data](#fixtures-and-data)
- [Turning findings into regression tests](#turning-findings-into-regression-tests)

## Deciding what the right answer is

Before you can call something a bug you need an oracle — a basis for saying the
observed behaviour is wrong. In descending order of authority:

1. **A written contract** — OpenAPI schema, type signature, documented error
   codes, a spec file. A divergence here is a bug with no argument available.
2. **Documentation and README examples.** If the documented example doesn't work,
   that is a finding whichever side is wrong, because users follow documentation.
3. **Consistency with the product's own siblings.** If eleven endpoints return
   `{"error": {"code": ...}}` and the twelfth returns a bare string, the twelfth is
   the bug.
4. **Reasonable user expectation.** Weakest, and still legitimate — a sort that
   puts `item10` before `item2` is wrong even if nothing says otherwise. Mark
   these as judgement calls in the report so the user can overrule you cheaply.

When you have no oracle at all, say so rather than inventing one. "This endpoint
accepts a negative `count` and returns an empty array; nothing documents which is
intended" is an honest and genuinely useful finding — it surfaces an unspecified
behaviour, which is where bugs breed.

## Deriving cases from a surface

For each input, the interesting values are the edges of each class it accepts, not
samples from the middle. A field accepting 1–100 has bugs at 0, 1, 100 and 101,
essentially never at 50 — so test 0, 1, 100, 101 and skip the middle. One value
per class, every edge of every class.

Then widen past the declared type. The question is not "what does this field
accept" but "what can reach this field", and the answer is anything the transport
allows: a client that isn't yours, a retry with a mangled body, a copy-paste from
a spreadsheet.

## The input catalogue

Run through this list against each input. Not every row applies to every field;
the ones that do take seconds each and are where defects concentrate.

**Absence and emptiness** — field omitted entirely; `null`; empty string; empty
array; empty object; whitespace only; a key present twice in the same JSON object.

**Numbers** — `0`; `-1`; the declared minimum and one below; the declared maximum
and one above; a float where an integer is expected; `1e309` (overflow to
infinity); `NaN`; a number sent as a string; a number with leading zeros;
`9007199254740993` (past JavaScript's exact-integer range); a negative zero.

**Strings** — one character; the length limit and one over; a value far over any
plausible limit (1MB in a name field); leading and trailing whitespace, which
systems disagree about trimming; embedded newlines and tabs; a null byte; control
characters; mixed line endings.

**Unicode** — accents in composed and decomposed forms, which compare unequal
byte-wise while looking identical; an emoji and a multi-codepoint emoji such as a
family sequence, which break naive character counting and truncation; right-to-left
text; a zero-width joiner; a right-to-left override, which makes `txt.exe` display
as `exe.txt`; a homoglyph such as Cyrillic `а` for Latin `a`, which matters anywhere
identity or uniqueness is checked; characters outside the Basic Multilingual Plane,
which break MySQL `utf8` (as opposed to `utf8mb4`) columns.

**Types and shapes** — a string where an object is expected and the reverse; an
array where a scalar is expected; a deeply nested object, 100 levels, which can
blow the parser's stack; an unexpected extra field, where both silent acceptance
and rejection are defensible but one of them is probably wrong here; correct JSON
with the wrong `Content-Type`; malformed JSON; a body sent with
`Content-Length: 0`.

**Identifiers and references** — an id that does not exist, which should be 404
and not 500; an id belonging to a different account, which is the authorization
test and belongs in `security` too; a deleted id; an id of the wrong format; a
valid id from a different resource type; the same id twice in one request.

**Dates and time** — a date before the epoch; a far-future date; February 30th; a
leap day; `23:59:60`; a timezone-naive value where one with a zone is expected and
the reverse; the DST spring-forward hour, which does not exist locally; an ordering
constraint inverted, with `end` before `start`.

**Files and uploads** — a zero-byte file; a file one byte over the limit; the
wrong extension for the real content and the reverse; a filename with a path
traversal sequence; a filename of 300 characters; a file whose declared MIME type
contradicts its magic bytes; an archive that expands enormously.

**Encoding and transport** — a URL-encoded value that decodes to a delimiter;
double encoding; a parameter supplied twice in a query string, where frameworks
disagree on which wins; the same parameter in both query string and body; an
unexpected HTTP method against the path; a HEAD where GET is expected.

Pick what is plausible for the surface rather than running all of it blindly. The
discipline that matters: look at this list per input rather than relying on
whichever three cases come to mind, because the ones that come to mind are the
ones already handled.

## State and sequence

Many defects need no unusual input at all, only an unusual order. For anything
holding state:

- **The empty state** — the product's first five minutes, before any data exists.
  Frequently the least-tested screen in the whole product.
- **The single-item state** — pagination, "and N others", and plural strings all
  break at exactly one.
- **The large state** — enough rows to hit the second page, the truncation, the
  query that was never indexed.
- **Replay** — the same create twice, the same submit twice, a double-clicked
  button.
- **Out-of-order** — delete then update; use a token after logout; complete a
  step whose prerequisite was skipped; resume a flow after the session expired.
- **Interrupted** — kill the process mid-write and restart; cancel an upload
  partway; close the tab mid-transaction. Then check what is left behind: a
  half-written record is worse than a failed one.
- **Resumption after error** — after a rejected request, is the resource still
  usable, or is it now wedged?

## The authorization matrix

Build the grid explicitly, because the gaps are invisible in prose. Rows are
callers, columns are surfaces, cells are expected outcome:

| Caller | Own resource | Another account's resource | Admin-only surface |
|---|---|---|---|
| Anonymous | 401 | 401 | 401 |
| Authenticated user | 200 | **404 or 403** | 403 |
| Admin | 200 | per policy | 200 |

Then test the cells, not just the diagonal. The cell in bold is where real
breaches live — an authenticated request for an object belonging to someone else,
where the code checked that you are logged in and forgot to check whose data it
is. Test it on every surface that takes an identifier, not just once per product;
these checks are written per handler and omitted per handler.

Also worth a pass: a token after logout, an expired token, a token for a deleted
user, a token with its signature stripped, a well-formed token from a different
environment, and a privileged action triggered through a path that bypasses the UI
that normally hides it.

## Concurrency and idempotency

Single-threaded tests pass on code that corrupts data under real traffic. Two
requests at once is enough to surface most of it:

- Two simultaneous creates with the same unique key — does one fail cleanly, or do
  both succeed and leave a duplicate?
- Two simultaneous updates to the same record — last-write-wins, a lock, or a lost
  update?
- Simultaneous decrements of a counter, quota or stock level — the classic
  read-modify-write race. Fire N concurrent requests against a quota of 1 and
  check that exactly one succeeded.
- A retry of a request whose response was lost — the client cannot tell timeout
  from success, so it will retry; does the retry double-charge, double-send,
  double-create?

`scripts/loadtest.py` with `--concurrency 20 --requests 20` is a serviceable race
prober for these, even though load is a different dimension.

## The error contract

Error paths carry the product's worst code because nobody looks at them. For each
failure you can provoke, check:

- **The status or exit code is the right one.** A 500 for malformed input is a
  bug: it tells the client to retry something that will never succeed, and it
  usually means an uncaught exception rather than a validation branch.
- **The message is actionable** — it names the field and the problem. "Invalid
  request" costs the user an afternoon.
- **The message leaks nothing** — no stack trace, no SQL, no file path, no
  internal hostname, no key material. This overlaps `security`; check it here
  because this is where you are already looking at error bodies.
- **The shape is consistent** with every other error the product returns, so a
  client can parse one thing.
- **Nothing partially happened.** Provoke a failure mid-operation and verify the
  state afterwards. A failed multi-step operation that left step one applied is a
  more expensive bug than the failure itself.

## Fixtures and data

Prefer real fixtures to mocks for the system under test. A mock encodes your
belief about a dependency's behaviour, so tests built on it verify your belief,
and pass right up until the dependency behaves differently. Mock only what you
cannot run — a paid third-party API, a service with no sandbox — and keep the mock
adjacent to a recorded real response so drift is visible.

Make fixtures deterministic. A test that depends on today's date, the current
time, random ids, map iteration order or network latency will fail on a Tuesday in
six months and be marked flaky rather than fixed. Freeze the clock, seed the
random source, sort before comparing.

## Turning findings into regression tests

Every confirmed finding gets a test that fails on today's code. Name it for the
behaviour rather than the bug — `rejects_negative_count` outlives
`issue_412_regression`, which means nothing to whoever reads it next year. Assert
the specific promise that was broken, not merely that the call did not throw.
