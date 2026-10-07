# Changelog

All notable changes to this skill are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-10-07

First release.

### Added

- `product-testing` skill covering four dimensions, selectable individually or run
  together: functionality and edge cases, UI and browser, load and resilience,
  security and abuse.
- A seven-step workflow built around a surface inventory, so testing starts from
  what the product exposes rather than from whatever the code review happened to
  surface.
- Evidence discipline: findings separate verified pass, verified failure and not
  tested, and every claim is tied to captured output.
- `scripts/surfaces.py` — surface inventory across common web, API, CLI and job
  frameworks, plus stack and test-harness detection.
- `scripts/loadtest.py` — concurrent HTTP load generator with latency percentiles,
  status histogram, classified errors and CI threshold gates. Standard library
  only; refuses non-local targets without an explicit acknowledgement.
- Severity rubric and report template in `assets/report-template.md`.
- A non-negotiable safety contract: authorization is per target and comes only from
  the user; destructive actions are never used as proof; surfaces that email,
  charge or notify need agreement; discovered secrets are reported by location, not
  value; product output is treated as data, never as instruction; and the skill
  stops at proof rather than escalating.
- A pre-handover verification checklist, so a pass nobody observed cannot be
  reported as one.
- Documentation set under `docs/`.
- Evaluation set under `evals/`: a fixture with ten verified planted defects, an
  answer key, a recall scorer, and the saved 7 Oct 2026 runs. Measured 10/10 recall
  with the skill against 9/10 without, with the substantive differences in
  deliverables and in restraint under identical authorization.
