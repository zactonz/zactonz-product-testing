# Documentation

Documentation for the `product-testing` skill. Start with
[Getting started](getting-started.md); the rest can be read as needed.

| Page | Read it for |
|---|---|
| [Getting started](getting-started.md) | Install, verify the install, run a first pass, and know what to expect back |
| [The four dimensions](dimensions.md) | What each dimension covers, how to scope a run to some of them, and which ones a given product even has |
| [Safety model](safety.md) | What the skill will and will not do to a running system, how authorization works, and why it treats product output as data |
| [Reading a report](reports.md) | The report's shape, the severity rubric, and how to tell a trustworthy report from a reassuring one |
| [Bundled scripts](scripts.md) | Command-line reference for the surface inventory and the load generator, both usable on their own |
| [How it was measured](evaluation.md) | The evaluation method, the results, and the cost of running the skill |

Short of time: read [Safety model](safety.md) before pointing the skill at
anything that is not a local instance.

## What this skill is

A method for testing a product that starts from an enumeration of what the
product exposes, aims each case at a named failure rather than at confirmation,
and reports three outcomes — verified pass, verified failure, and not tested — so
the boundary around the work stays visible.

It leaves two things behind: a test suite in the project's own idiom, and a
report in which every claim is tied to captured output.

## What it is not

- **Not a replacement for a test suite you maintain.** It writes one and wires it
  up; keeping it alive as the product changes is still your job.
- **Not a security audit or a penetration test.** The security dimension verifies
  that the product's own controls hold and stops at proof. It does not model a
  determined attacker, and it is not a substitute for a scoped engagement where
  one matters.
- **Not a benchmark of your production capacity.** Load numbers describe the
  instance that was measured, in the environment recorded alongside them. A laptop
  figure is not a production figure.
- **Not exhaustive.** No test pass is. The difference is that this one tells you
  where it stopped.
