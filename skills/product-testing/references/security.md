# Security and abuse testing

Read this when running the `security` dimension. The goal is to verify that the
product's own protections hold — that authorization is checked on every surface,
that input cannot change the meaning of a query or a page, and that secrets stay
out of responses and logs.

## Contents

- [Scope, and where to stop](#scope-and-where-to-stop)
- [Posture](#posture)
- [Authorization](#authorization)
- [Authentication and sessions](#authentication-and-sessions)
- [Injection](#injection)
- [Requests the server makes for you](#requests-the-server-makes-for-you)
- [Secret leakage](#secret-leakage)
- [File handling](#file-handling)
- [Transport and headers](#transport-and-headers)
- [Configuration and dependencies](#configuration-and-dependencies)
- [Abuse and cost](#abuse-and-cost)
- [Reporting a security finding](#reporting-a-security-finding)

## Scope, and where to stop

Test only what the user owns or is authorized to test, and only the instance they
named. This dimension needs that stated once, explicitly, before the first probe —
not because of ceremony, but because the same request is routine against your own
staging server and a criminal offence against someone else's.

Stay inside these lines throughout:

- **Prefer a non-production instance.** Several checks here write data or trip
  alarms.
- **Stop at proof, and do not pivot.** Once a control is shown to be missing, the
  finding is complete. Reading one record that should have been denied proves the
  flaw; enumerating the table does not add information and does turn a test into a
  breach. Never move from one weakness to deeper access, and never touch another
  account's data beyond the single read that demonstrates the gap.
- **Do not destroy to demonstrate.** Prove a missing check with a read, or a write
  to a record you created. Never delete, overwrite or modify real data as a proof.
- **Handle what you find as confidential.** If a probe surfaces real credentials or
  personal data, record that it was exposed and where — not the value. Put nothing
  live into a report, a screenshot, a test fixture or a commit, and tell the user
  immediately so they can rotate.
- **Report rather than exploit third-party flaws.** A weakness in a dependency or
  an upstream service gets written up and reported upstream, not exercised.

If the user asks for something beyond this — exploitation of a system they do not
control, bypassing another party's protections, anything aimed at a live target
without authorization — decline that part, say which part, and carry on with the
rest.

## Posture

Think in terms of controls rather than exploits. For each control the product
relies on, construct the minimum request that shows whether it is present:

> Does the handler check *whose* record this is, or only that someone is logged in?

A single `curl` with the wrong account's token answers that. You are not building
a weapon; you are checking that a door is locked, and one turn of the handle is
the whole test.

Work from the surface inventory, not from a checklist of vulnerability names. The
inventory tells you where user input enters, where authorization is required and
where the server acts on a value it was handed — and that is where the defects
are.

## Authorization

Broken authorization is the most common serious flaw in working software, because
the check is written per handler and therefore forgotten per handler. It is also
the cheapest thing to test, so test it first and test it everywhere.

Create two accounts, A and B, each with a resource of their own. Then for every
surface that takes an identifier:

- A requests B's resource by id → must be denied, 403 or 404, never 200
- A updates or deletes B's resource → denied
- A lists resources → sees only its own, with nothing of B's leaking through a
  count, a total, an aggregate or an error message
- A supplies B's id in a nested field, a filter, a sort key, an include parameter
  or a webhook target, not just in the path — the path is usually the only place
  the check was added
- A requests an admin surface → denied
- A escalates its own role by sending a `role`, `is_admin`, `plan` or `account_id`
  field in an update to its own profile → must be ignored. Mass assignment of a
  privileged field is a complete privilege escalation and takes one request to
  check
- An unauthenticated caller requests each surface → denied, with no detail in the
  response body about whether the resource exists

Identifier shape matters to severity, not to correctness. Sequential integers make
an exposure trivially exploitable; opaque UUIDs make it harder. Neither is an
authorization check, and a missing check behind a UUID is still a missing check.

Also check the surfaces that have no caller in the repo — admin paths, debug
endpoints, queue consumers, webhook receivers, export and import routes, health
endpoints that return configuration. Protection tends to live in the UI that hides
them, which is no protection at all.

## Authentication and sessions

- Credentials are verified server-side, every time, and the response is the same
  shape and timing whether the account exists or not
- A wrong password, an unknown user and a locked account are indistinguishable
  from outside, so the endpoint cannot be used to enumerate users
- Tokens are rejected when expired, when the signature is stripped, when the
  algorithm is changed to `none`, when signed with a different or empty key, and
  when issued by a different environment
- Logout invalidates server-side, not only in the client. Replay the token
  afterwards and confirm it fails
- Password reset tokens are single-use, time-limited, unguessable, and bound to one
  account. Using a token for account A on account B must fail
- Changing a password or email invalidates other sessions, or tells the user it
  did not
- Session cookies carry `HttpOnly`, `Secure` and a `SameSite` value
- The login and reset endpoints are rate-limited per account as well as per IP
- Multi-factor enrolment cannot be skipped by calling the post-enrolment endpoint
  directly

## Injection

The pattern is the same in every variant: input crosses into a context where it is
interpreted as syntax instead of data. One probe per context is enough to tell
whether the boundary holds.

- **SQL** — send `'` and `"` in each parameter that could reach a query, including
  numeric ones, and watch for a database error, a 500, or a changed result set. A
  returned syntax error is proof of concatenation; stop there, and do not go on to
  extract anything. Also check `ORDER BY`, `LIMIT`, column names and table names
  passed through from the request, which parameterisation does not cover
- **Cross-site scripting** — submit a benign, non-destructive marker such as
  `<zxss>` in each field, then look at where it is rendered. If it appears
  unescaped in HTML, in an attribute, inside a `<script>`, or in a `javascript:`
  URL, the escaping is missing. Check the stored path too: a value escaped on the
  page that wrote it and not on the page that reads it back is the classic stored
  case. Include the error pages that echo input, and search results, which are
  often the only unescaped surface
- **Command execution** — wherever input reaches a shell, an image converter, a
  PDF renderer, an archive tool, a `git` call or a DNS lookup, check that arguments
  are passed as an array rather than an interpolated string, and that a value
  beginning with `-` is not taken as a flag. Probe with a benign separator and look
  for a changed error message, not with a payload that does anything
- **Server-side template injection** — where user input lands in a template,
  send `{{7*7}}` or the engine's equivalent and see whether `49` comes back.
  Email templates and customisable messages are where this hides
- **Path traversal** — send `../`, its URL-encoded and double-encoded forms, and
  an absolute path, to every parameter naming a file, a path, a locale, a theme or
  a template. Confirm the result is a rejection rather than a file
- **XML** — if XML is accepted, confirm external entities are disabled, since the
  default in several parsers is to resolve them
- **Deserialization** — if the product deserializes anything user-supplied with a
  format that can instantiate objects, that is a finding on its own; it does not
  need a working chain to be worth reporting
- **Header and log injection** — send a newline in a value that ends up in a
  response header or a log line, and check it is stripped

For each, the finding is "this boundary is not enforced", evidenced by the error
or the reflected marker. Resist going further; proof of the gap is the deliverable.

## Requests the server makes for you

Any surface that takes a URL and fetches it — a webhook target, an image importer,
a link previewer, a PDF generator, an avatar-from-URL field, an OAuth redirect, a
feed reader — can be pointed inward. This is worth real attention because cloud
metadata endpoints and internal services usually require no authentication at all.

Check that the product refuses, after DNS resolution and after every redirect:

- loopback and link-local addresses, including the metadata address `169.254.169.254`
- private ranges — `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- schemes other than `http` and `https`, such as `file:`, `gopher:` or `dict:`
- a hostname that resolves to a private address, which a deny-list of literal IPs
  does not catch
- a redirect from a public URL to a private one, which is where most
  implementations fail, because the first URL was validated and the second was not
- an address that resolves differently on the second lookup than the first

Also confirm the fetch is bounded: a size cap, a timeout, a redirect limit, and a
response that is not echoed back verbatim to the caller.

## Secret leakage

Search systematically; this is where the quick wins are:

- **Responses** — does any response include a password hash, an internal id, a
  full user record where a name was needed, another user's data, a token, or an
  API key? Compare against what the endpoint is documented to return
- **Errors** — provoke a 500 and read the body. A stack trace, a SQL statement, a
  file path, a framework version banner or a connection string in an error page is
  a finding, and the fix — turn debug mode off in production — is one line
- **Headers** — `Server`, `X-Powered-By` and framework version headers give an
  attacker a version to look up
- **The client bundle** — grep the built JavaScript, the source maps and the HTML
  for keys, internal hostnames and commented-out endpoints. Anything shipped to the
  browser is public, and a service-role key committed into a front-end bundle is a
  total compromise
- **Public paths** — check for `.git/`, `.env`, `.env.bak`, `config.php.bak`,
  `composer.lock`, `package.json`, `*.sql`, `/backup/`, `phpinfo.php`,
  `/.well-known/` and the framework's debug route, all reachable over HTTP
- **Repository history** — `git log -p -S'<marker>'` for keys that were committed
  and later deleted. Deleting a secret in a later commit does not remove it, and
  the history is usually public
- **Logs** — tokens, passwords, card numbers, full request bodies and personal data
  written to a log that is kept forever and read by anyone

When you find a live secret: report its location and nothing of its value, and tell
the user at once that it needs rotating rather than only deleting.

## File handling

- The type is decided by content, not by extension or by the client's declared
  `Content-Type`
- An executable or script extension is rejected, including double extensions and
  the ones the web server might execute by configuration
- Uploads are stored outside the web root, or served with
  `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff` so the
  browser cannot be tricked into executing them
- A size limit exists and is enforced before the file is buffered entirely into
  memory
- Filenames are sanitised: no traversal, no null bytes, no overwriting another
  user's file by choosing their name
- An SVG upload is treated as active content, because it can carry script
- An archive is checked for expansion ratio and for entries with absolute or
  traversing paths
- A download endpoint checks authorization on the file, not only that the caller is
  logged in — this is the authorization test again, and it is very often missing on
  file routes

## Transport and headers

- HTTPS everywhere, with HTTP redirecting to it
- `Strict-Transport-Security` present
- A certificate that is valid, matches the host, and is not near expiry
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options` or a `frame-ancestors` policy, if the product should not be
  framed
- A Content-Security-Policy that actually constrains something — one allowing
  `unsafe-inline` and `*` is decoration
- CORS that does not reflect an arbitrary `Origin` back with
  `Access-Control-Allow-Credentials: true`, which is equivalent to no
  same-origin policy at all. Test with an origin you choose and see what comes back
- State-changing requests protected against cross-site forgery, by token or by
  `SameSite`, and verify the protection is enforced rather than merely issued

## Configuration and dependencies

- Debug and development modes off; no debug toolbar, no verbose errors, no test
  routes
- Default or seeded credentials changed, and any sample admin account removed
- Directory listing off
- Known-vulnerable dependencies: `npm audit`, `composer audit`, `pip-audit`,
  `govulncheck` — whichever applies. Report what the tool says, and check whether
  the vulnerable path is actually reachable in this product before assigning a
  severity, since most advisories in a dependency tree are not
- Secrets supplied by environment or a secret store, not committed
- Database and cache not listening on a public interface

## Abuse and cost

Worth checking wherever a request costs the user money or sends something to a
third party:

- An unauthenticated or cheap request that triggers an expensive operation — an
  AI completion, an image conversion, an email, an SMS, a third-party API call —
  with no rate limit, which is a direct route to a large bill
- An endpoint that can be made to send mail to an address the attacker chooses,
  with content they influence
- A quota enforced non-atomically, so concurrent requests overshoot it; see the
  concurrency section of `load.md`
- An expensive search or report endpoint with no limit on result size or query
  complexity
- Anything accepting an unbounded list, where one request becomes ten thousand
  operations

## Reporting a security finding

Per finding, in this order:

1. **What control is missing**, in one sentence — "the resource handler checks
   authentication but not ownership".
2. **Where** — the exact surface, file and line if you have it.
3. **The minimum reproduction** — one request, with the account context stated,
   and secrets redacted.
4. **What an attacker gets** — concretely, and bounded by what you actually
   verified. "Any authenticated user can read any other account's invoices" is
   useful; "full compromise" without evidence is not.
5. **Severity**, by the rubric in `reporting.md`, judged on impact and on how
   reachable the flaw is rather than on how alarming its name sounds.
6. **The fix**, specifically — which check to add, where.

Lead the report with these. A missing authorization check outranks every
functionality finding in the same report, and it should not be the ninth item the
user reads.
