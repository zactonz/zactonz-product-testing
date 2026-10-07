# Getting started

## Requirements

| Component | Needed for |
|---|---|
| Claude Code | the skill |
| Python 3.9 or newer | the two bundled scripts |
| A browser driver | the UI dimension only — see below |

Nothing else. The scripts use the Python standard library, so there is no install
step and nothing to keep up to date.

For the UI dimension the skill uses whatever is already available, in this order:
the session's own browser tools; a driver the project already has (Playwright,
Cypress, Puppeteer); otherwise it says so and falls back to asserting
server-rendered HTML, which checks markup but not rendering. It will not install a
browser without asking.

## Install

As a plain skill — copying the folder is the whole operation, and there is nothing
to build:

```bash
git clone https://github.com/zactonz/zactonz-product-testing.git
cp -r zactonz-product-testing/skills/product-testing ~/.claude/skills/
```

Or as a Claude Code plugin. A plugin resolves through a marketplace, so the
marketplace is registered first and the plugin installed from it — `/plugin
install` on its own will not find it:

```bash
/plugin marketplace add zactonz/zactonz-product-testing
/plugin install zactonz-product-testing@zactonz-product-testing
```

Installed as a plugin, the skill is addressed as
`zactonz-product-testing:product-testing`.

Use `./.claude/skills/` instead of `~/.claude/skills/` to scope it to one project.
Either way, start a new session afterwards so the skill is picked up.

## Verify the install

```bash
python3 ~/.claude/skills/product-testing/scripts/surfaces.py --help
python3 ~/.claude/skills/product-testing/scripts/loadtest.py --help
```

Both should print usage. If `surfaces.py` runs but Claude never seems to use the
skill, check that `SKILL.md` sits directly inside the skill folder rather than one
level down — `~/.claude/skills/product-testing/SKILL.md`.

## Run a first pass

Ask in the ordinary way; the skill triggers on its own.

```
test the export endpoint before I ship it
can the API handle Black Friday traffic?
find the edge cases in the invoice form
is this upload handler safe?
full QA pass on the dashboard
```

To scope deliberately, name the dimensions: *run the load and security dimensions
against the staging API*. Naming none runs all four.

## What happens, in order

1. **Scope.** It establishes what is under test — the commit or version, the URL,
   the environment — and settles authorization if load or security work is
   involved. Expect to be asked before any traffic goes at something live.
2. **Inventory.** It enumerates the product's surfaces rather than testing from
   whatever a code skim surfaced. This is the step that decides whether the rest is
   real.
3. **Plan.** A short table of surfaces and the cases chosen for each. On a large or
   ambiguously scoped product it will show you this before a long run.
4. **Execute.** Dimension by dimension, capturing raw output as it goes.
5. **Suite.** Tests written into the project's existing test location, in its
   existing idiom, wired to one command.
6. **Report.** A verdict, ranked findings with minimal reproductions, and an
   explicit list of what was not tested.

## What you get back

- **A report** at `test-reports/<date>-<scope>/report.md` by default, with the
  evidence beside it. See [Reading a report](reports.md).
- **A test suite** where the project's tests already live. Every confirmed finding
  gets a test that fails today — those are the regression guards, and they flip
  green as each fix lands, which is a better signal that a fix worked than
  re-reading the diff.
- **The raw captures** the report rests on, so any claim can be checked.

Evidence files can carry real payloads and screenshots. The skill will say so and
ask before committing them; decide whether that directory belongs in git.

## Scoping advice

The skill is worth reaching for on a pre-release pass, after a refactor that
touched many surfaces, when inheriting an unfamiliar codebase, or when you need a
defensible answer to "is this ready". It costs roughly 1.8× the tokens and 2.3×
the time of testing without it — see [How it was measured](evaluation.md) — which
is plainly worth it for those, and not worth it for a one-line sanity check.

On a large product, scope the first run to one dimension and a handful of surfaces
rather than asking for everything. A focused pass that finishes beats a broad one
that runs out of room, and the inventory from the first run makes the next one
cheaper.
