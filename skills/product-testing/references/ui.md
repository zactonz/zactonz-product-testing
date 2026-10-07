# UI and browser testing

Read this when running the `ui` dimension. The goal is to verify what a person
actually sees and can do, in a real browser, rather than what the markup suggests
they would.

## Contents

- [Pick a driver](#pick-a-driver)
- [Read as text, screenshot for proof](#read-as-text-screenshot-for-proof)
- [What to check](#what-to-check)
- [Interaction](#interaction)
- [Forms](#forms)
- [Responsive and theme](#responsive-and-theme)
- [Accessibility](#accessibility)
- [Console and network](#console-and-network)
- [Visual regression](#visual-regression)
- [Not being flaky](#not-being-flaky)
- [Evidence](#evidence)

## Pick a driver

Check what exists before planning around a tool:

```bash
for t in npx playwright node python3 chromium google-chrome; do printf '%-18s' "$t"; command -v $t >/dev/null && echo present || echo absent; done
ls node_modules/.bin 2>/dev/null | grep -Ei 'playwright|cypress|puppeteer|webdriver|vitest|jest' || true
grep -rslE 'playwright|cypress|puppeteer|selenium' --include=package.json --include=*.toml --include=*.txt . 2>/dev/null | head
```

| Situation | Driver |
|---|---|
| Interactive session with browser tools available | The session's own browser tools — fastest path, no install, and the user watches along |
| The project already has Playwright, Cypress or Puppeteer | That one, in its existing idiom, so the suite you leave runs with the rest |
| Durable suite needed and nothing installed | `npx playwright test` — one install, bundled browsers, built-in waiting, and it is the current default for new work |
| No browser available at all | Say so in **Not tested** and fall back to asserting server-rendered HTML with a parser. Note the limit plainly: this verifies markup, not rendering, and will not catch a CSS or JavaScript failure |

Never conclude a UI works from reading source alone. Layout breaks, scripts throw,
fonts fail to load, and a stylesheet 404 leaves markup that parses perfectly and
renders as an unstyled column. Rendering is the thing under test.

## Read as text, screenshot for proof

Reading the accessibility tree or page text is cheaper, more precise and more
reliable than reading a screenshot for anything textual — content, structure,
element state, whether a control is disabled. Screenshots are for what only an
image can settle: layout, overlap, spacing, colour, truncation, and for the
evidence you attach to a finding.

So: drive and assert through text, then take one screenshot per confirmed visual
finding and one per major state you want to prove.

## What to check

Walk the inventory's pages. For each one:

- It renders at all — no blank page, no error overlay, no raw template syntax
  leaking through, no visible `undefined`, `null`, `NaN`, `[object Object]` or
  unresolved `{{placeholder}}`
- Its real content is present, not just its chrome. A page whose shell renders
  while the data fetch failed looks fine in a screenshot and is useless
- Loading, empty, error and populated states each render deliberately. The empty
  state is the most-skipped screen in software and the first one a new user sees
- Long and short content both survive: a 200-character title, a name with no
  spaces, a list of one, a list of 500, a missing avatar, a missing image
- Nothing overlaps, clips or overflows the viewport horizontally
- Navigation works in both directions, including the browser back button, which
  single-page applications routinely break
- A deep link to the page works in a fresh session — direct entry, not reached by
  clicking from the home page, which is how every shared link arrives

## Interaction

Click the things. Then verify the consequence through text, not by assuming:

- Every primary action, and the state it produces
- Double-clicking a submit button — does it fire twice?
- Clicking while a request is in flight; a button that stays enabled during its
  own request is a duplicate-submission bug waiting for a slow network
- Keyboard-only operation of each flow: `Tab` to reach, `Enter` and `Space` to
  activate, `Escape` to dismiss. A control reachable only by mouse excludes real
  users and usually signals a `div` doing a button's job
- Focus behaviour around modals: focus moves in on open, is trapped inside, and
  returns to the trigger on close
- Destructive actions confirm first, and cancelling the confirmation really
  cancels

## Forms

Forms concentrate UI defects because they hold state, validate, and submit:

- Submit empty — every required field should be flagged at once, not one at a time
- Submit with each field individually invalid, using the string and number rows of
  the catalogue in `functionality.md`
- Paste rather than type, which bypasses `keypress` handlers that some validation
  depends on
- Autofill, which bypasses them too
- Leading and trailing whitespace in each field
- Validation messages are programmatically associated with their field, so a
  screen reader announces them, rather than being coloured text nearby
- The error state survives a failed submit without wiping what was typed — losing
  a filled-in form on a server error is among the most expensive small bugs there is
- Submit twice rapidly
- Browser back after a successful submit

## Responsive and theme

Check 375px wide (phone), 768px (tablet) and the default desktop width. At the
narrow end specifically: no horizontal page scroll, text not clipped, tap targets
not overlapping, modals and tables still usable, the nav reachable.

If the product supports light and dark, check both. Bugs cluster in exactly two
places — text whose colour was set without a matching background, which vanishes
in the other theme; and a hardcoded white or black that survives the theme switch
and leaves a glaring panel. Also test the system preference itself, not only an
in-page toggle, because the two code paths are often separate and only one is
wired up.

## Accessibility

Automated scanning catches a real fraction of problems and nearly all the cheap
ones. If `axe-core` can be loaded into the page, run it; otherwise `pa11y`, or
Lighthouse's accessibility category. Scan each distinct page template rather than
every page, since templates repeat.

Then check by hand the things no scanner can judge:

- **Contrast** — 4.5:1 for body text, 3:1 for large text and for the visual
  boundary of interactive controls. Scanners find most of this; placeholder text
  and disabled states are where they commonly do not
- **Focus visibility** — every focusable element has a visible indicator. A reset
  stylesheet that removed outlines without replacing them is the usual cause, and
  it makes keyboard use impossible while looking tidy
- **Images** — meaningful ones have alt text that conveys the meaning; decorative
  ones have empty alt so they are skipped rather than read as a filename
- **Headings** — one `h1`, no skipped levels, and the structure matches the visual
  hierarchy, since that structure is how screen-reader users navigate
- **Labels** — every input has one, associated by `for`/`id` or wrapping. A
  placeholder is not a label: it disappears on focus and is often invisible to
  assistive technology
- **Links** — the text says where it goes. Several "click here" links on a page are
  indistinguishable in a link list
- **Live regions** — content that changes without navigation (toasts, results
  counts, validation summaries) is announced
- **Motion** — animation respects `prefers-reduced-motion`
- **Zoom** — the page is usable at 200% browser zoom

## Console and network

Read both on every page, because they expose failures that leave no visible trace:

- Any uncaught exception is a finding, even on a page that looks correct — it
  means a handler stopped partway, and the consequence surfaces later as a stuck
  button
- Any 4xx or 5xx, including the ones for assets. A 404 stylesheet or font changes
  the rendering invisibly; a 404 analytics beacon is noise worth noting once
- Mixed content, CSP violations, CORS failures
- Requests fired on every render, or the same request fired several times, which
  is a performance bug visible only here
- Anything sensitive in a URL — a token, an email address, an id in a query string
  that will end up in logs, referrers and browser history

## Visual regression

Worth setting up only if the user wants ongoing protection against unintended
visual change. Playwright's `toHaveScreenshot` handles baselines and diffing.
Before committing baselines, mask or freeze what changes on its own — clocks,
relative dates, random content, animations, cursors — or the suite fails daily and
gets switched off. Without that discipline, skip it: a visual suite nobody trusts
is worse than none.

## Not being flaky

UI flake comes from racing the page rather than from the browser:

- Wait for a condition, never a duration. `sleep(2)` is both slower than needed
  and still too short on a loaded machine
- Wait for the thing you are about to assert on, not for a general idea of
  readiness. Networks going idle does not mean the element has rendered
- Prefer role- and text-based selectors over CSS paths; `nth-child` chains break
  on every markup change and hide what the test meant
- Disable animations in the test environment, or wait for them to settle
- Give each test its own state. Tests that share a logged-in session or a record
  pass alone and fail in sequence
- Scope network stubbing precisely, so a stub for one request does not silently
  swallow another

## Evidence

Per finding: the URL, the viewport, the browser, the exact steps, a screenshot of
the broken state, and the console or network output if either is implicated. For
anything intermittent, say how many of how many runs reproduced it — that number
is what tells the user whether to chase it now.
