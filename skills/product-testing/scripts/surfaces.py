#!/usr/bin/env python3
"""Inventory the surfaces a codebase exposes, as a first pass before testing.

Greps a pattern library covering common web, API, CLI and job frameworks and groups
what it finds: routes, CLI entry points, pages, specs, scheduled work, auth checks,
outbound requests, uploads, raw SQL and possible hardcoded secrets. It also reports
the detected stack and any test harness already present.

This is a starting point, not an authority. Dynamically registered routes, surfaces
behind indirection and anything generated at runtime will not appear, so follow it
with the route table, the API spec and `--help` output. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "vendor", "bower_components", "dist",
    "build", "out", ".next", ".nuxt", ".svelte-kit", "target", "__pycache__",
    ".venv", "venv", "env", "site-packages", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", "coverage", ".cache", ".idea", ".vscode", "Pods",
    ".gradle", ".terraform", "bin-release", "tmp", "logs", "test-reports",
    "worktrees", "wp-content", "Carthage", "DerivedData",
}
KEEP_HIDDEN_DIRS = {".github"}  # scheduled workflows live here and are a real surface
SKIP_FILE_RE = re.compile(r"\.(min\.js|min\.css|map|lock|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|eot|pdf|zip|gz|tgz|bz2|xz|mp4|mp3|wav|so|dylib|dll|exe|class|jar|pyc|wasm)$", re.I)
SCAN_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".php", ".rb", ".go",
    ".java", ".kt", ".cs", ".rs", ".swift", ".ex", ".exs", ".pl", ".sh", ".bash",
    ".zsh", ".html", ".htm", ".vue", ".svelte", ".twig", ".blade", ".erb", ".ejs",
    ".hbs", ".yaml", ".yml", ".json", ".toml", ".ini", ".conf", ".env", ".graphql",
    ".gql", ".sql", ".tf", ".htaccess", ".cfg", "",
}
MAX_BYTES = 2_000_000
PER_FILE_CAP = 3  # one noisy file must not crowd out every other file in a category

# (category, label, pattern[, only-these-filenames][, skip-these-filenames])
PATTERNS: list[tuple] = [
    ("http_routes", "express/koa/fastify", re.compile(r"\b(?:app|router|server|fastify|api|route)\s*\.\s*(get|post|put|patch|delete|options|head|all)\s*\(\s*['\"`]([^'\"`\n]{0,120})")),
    ("http_routes", "flask/fastapi decorator", re.compile(r"@\s*(?:app|router|api|bp|blueprint)\w*\s*\.\s*(get|post|put|patch|delete|route|websocket)\s*\(\s*['\"]([^'\"\n]{0,120})")),
    ("http_routes", "django urlconf", re.compile(r"\b(?:path|re_path|url)\s*\(\s*r?['\"]([^'\"\n]{0,120})['\"]\s*,")),
    ("http_routes", "laravel", re.compile(r"Route::\s*(get|post|put|patch|delete|any|match|resource|apiResource|view|redirect)\s*\(\s*['\"]([^'\"\n]{0,120})")),
    ("http_routes", "rails routes", re.compile(r"^\s*(get|post|put|patch|delete|resources?|root|namespace|scope)\s+['\":/]([^'\"\n]{0,120})")),
    ("http_routes", "go net/http & routers", re.compile(r"(?:http\.HandleFunc|mux\.(?:HandleFunc|Handle)|\w+\.(?:Get|Post|Put|Patch|Delete|GET|POST|PUT|PATCH|DELETE|Handle|HandleFunc))\s*\(\s*['\"`]([^'\"`\n]{0,120})")),
    ("http_routes", "spring mapping", re.compile(r"@(?:Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?['\"]?([^'\"\n)]{0,120})")),
    ("http_routes", "asp.net", re.compile(r"\[(?:Http(?:Get|Post|Put|Patch|Delete)|Route)\s*\(\s*['\"]?([^'\"\n)]{0,120})")),
    ("http_routes", "wordpress rest", re.compile(r"register_rest_route\s*\(\s*['\"]([^'\"\n]{0,120})")),
    ("http_routes", "wordpress ajax/admin-post", re.compile(r"add_action\s*\(\s*['\"](?:wp_ajax_|wp_ajax_nopriv_|admin_post_)([^'\"\n]{0,120})")),
    ("http_routes", "rewrite rule", re.compile(r"^\s*RewriteRule\s+(\S{0,120})")),
    ("http_routes", "raw php superglobal entry", re.compile(r"\$_(?:GET|POST|REQUEST)\s*\[\s*['\"]([^'\"\n]{0,80})")),
    ("http_routes", "request uri dispatch", re.compile(r"REQUEST_URI|PATH_INFO|parse_url\s*\(\s*\$_SERVER")),

    ("api_specs", "openapi/swagger", re.compile(r"^\s*[\"']?(?:openapi|swagger)[\"']?\s*:\s*[\"']?\d")),
    ("api_specs", "graphql type/schema", re.compile(r"^\s*(?:type\s+(?:Query|Mutation|Subscription)\b|schema\s*\{)")),
    ("api_specs", "json schema", re.compile(r"[\"']\$schema[\"']\s*:")),

    ("cli_entrypoints", "shebang", re.compile(r"^#!\s*/\S*(?:bin/)?(?:env\s+)?(python3?|node|php|ruby|bash|sh|perl)\b")),
    ("cli_entrypoints", "python argparse/click/typer", re.compile(r"argparse\.ArgumentParser\s*\(|@\s*(?:click|app|cli)\.(?:command|group)\s*\(|typer\.Typer\s*\(")),
    ("cli_entrypoints", "node commander/yargs", re.compile(r"\b(?:new\s+Command\s*\(|require\s*\(\s*['\"](?:commander|yargs)|from\s+['\"](?:commander|yargs))")),
    ("cli_entrypoints", "go flag/cobra", re.compile(r"flag\.(?:Parse|String|Int|Bool)\s*\(|cobra\.Command\s*\{")),
    ("cli_entrypoints", "php cli dispatch", re.compile(r"\$argv\s*\[|php_sapi_name\s*\(\s*\)\s*===?\s*['\"]cli")),
    ("cli_entrypoints", "wp-cli command", re.compile(r"WP_CLI::add_command\s*\(")),

    ("ui_pages", "react router", re.compile(r"<Route\b[^>]{0,200}?path\s*=\s*[\"'{]([^\"'}\n]{0,120})")),
    ("ui_pages", "vue router", re.compile(r"\bpath\s*:\s*['\"]([^'\"\n]{0,120})['\"]\s*,\s*(?:name|component|children)")),
    ("ui_pages", "html document", re.compile(r"<!DOCTYPE\s+html|<html[\s>]", re.I)),
    ("ui_pages", "template render", re.compile(r"\b(?:render_template|res\.render|view\s*\(|\$this->render|render\s*\(\s*['\"])([^'\"\n]{0,80})")),

    ("scheduled_jobs", "cron expression", re.compile(r"^\s*(?:[-\d*/,]+\s+){4}[-\d*/,]+\s+\S"), re.compile(r"(?i)(?:^|[./])(?:cron|crontab)")),
    ("scheduled_jobs", "github actions schedule", re.compile(r"^\s*-?\s*cron\s*:")),
    ("scheduled_jobs", "laravel/rails/node scheduler", re.compile(r"\$schedule->|schedule\.every\s*\(|new\s+CronJob\s*\(|node-cron|setInterval\s*\(")),
    ("scheduled_jobs", "celery/rq/sidekiq task", re.compile(r"@(?:shared_task|celery\.task|app\.task)\b|include\s+Sidekiq::Worker|Resque\.enqueue")),
    ("scheduled_jobs", "queue worker", re.compile(r"\b(?:new\s+Worker\s*\(|Queue\s*\(\s*['\"]|dispatch\s*\(\s*new\s+|->onQueue\s*\()")),
    ("scheduled_jobs", "wordpress cron", re.compile(r"wp_schedule_(?:single_)?event\s*\(|add_action\s*\(\s*['\"][a-z_]*cron")),

    ("webhooks_events", "webhook route or handler", re.compile(r"(?i)\bwebhook[s]?\b")),
    ("webhooks_events", "signature verification", re.compile(r"(?i)X-Hub-Signature|Stripe-Signature|hmac[_-]?(?:sha|verify)|constructEvent\s*\(")),
    ("webhooks_events", "event listener registration", re.compile(r"add_action\s*\(\s*['\"]|addEventListener\s*\(\s*['\"]|\.on\s*\(\s*['\"](?:message|connection|request|error|data|close|webhook)['\"]")),

    ("auth_boundaries", "auth middleware/guard", re.compile(r"(?i)\b(?:require(?:s)?_?auth|authenticate|authorize|login_required|ensureAuthenticated|middleware\s*\(\s*['\"]auth|before_action\s*:\s*authenticate|\[Authorize\b)")),
    ("auth_boundaries", "role or capability check", re.compile(r"(?i)\b(?:is_?admin|has_?role|current_user_can|user_?can|hasPermission|checkPermission|can\s*\(\s*['\"]|@PreAuthorize)")),
    ("auth_boundaries", "token or key handling", re.compile(r"(?i)\b(?:Authorization['\"]?\s*[:=\]]|Bearer\s|api[_-]?key|jwt\.(?:verify|decode)|verify_?token)")),
    ("auth_boundaries", "csrf/nonce", re.compile(r"(?i)\b(?:csrf|wp_verify_nonce|check_admin_referer|verify_?nonce|authenticity_token)")),
    ("auth_boundaries", "ownership check", re.compile(r"(?i)\b(?:user_?id\s*(?:==|===|!=|!==)|->user_id\s*(?:==|!=)|account_?id\s*(?:==|===))")),

    ("outbound_requests", "http client call", re.compile(
        r"(?:(?<![\w>.])fetch|\baxios\.(?:get|post|put|patch|delete|request)"
        r"|\brequests\.(?:get|post|put|patch|delete)|\burlopen|\bcurl_exec|\bcurl_init"
        r"|\bwp_remote_(?:get|post|request)|\bHttpClient|\bhttp\.(?:Get|Post)"
        r"|\bRestTemplate|\bfile_get_contents)\s*\("
    )),
    ("outbound_requests", "url taken from input", re.compile(r"(?i)\b(?:url|uri|endpoint|callback|redirect|target|src|image_url|webhook_url)\b\s*[=:]\s*(?:\$_|request\.|req\.(?:body|query|params)|params\[|input\(|getenv)")),

    ("file_uploads", "upload handling", re.compile(r"\$_FILES|move_uploaded_file\s*\(|request\.files|multer\s*\(|MultipartFile|FormData\s*\(|multipart/form-data|ActiveStorage")),

    ("raw_sql", "sql statement in source", re.compile(r"(?i)\b(?:SELECT\s+[\w*`\"\[].{0,200}?\bFROM\b|INSERT\s+INTO\b|UPDATE\s+\w+\s+SET\b|DELETE\s+FROM\b|DROP\s+TABLE\b)"), None, re.compile(r"\.sql$", re.I)),
    ("raw_sql", "query built by interpolation", re.compile(r"(?i)(?:query|execute|prepare|exec)\s*\(\s*[\"'`][^\"'`\n]{0,160}(?:\$\{|\"\s*\+|\.\s*\$|%s\b|f[\"'])")),

    ("possible_secrets", "assigned literal secret", re.compile(r"(?i)\b(?:api[_-]?key|secret|password|passwd|token|access[_-]?key|private[_-]?key|client[_-]?secret)\b\s*[:=]\s*[\"'][A-Za-z0-9_\-/+=.]{16,}[\"']")),
    ("possible_secrets", "known key prefix", re.compile(r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_\-]{30,})")),
    ("possible_secrets", "private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
]

STACK_FILES = {
    "package.json": "Node / JavaScript",
    "composer.json": "PHP / Composer",
    "requirements.txt": "Python / pip",
    "pyproject.toml": "Python",
    "Pipfile": "Python / pipenv",
    "go.mod": "Go",
    "Gemfile": "Ruby",
    "Cargo.toml": "Rust",
    "pom.xml": "Java / Maven",
    "build.gradle": "Java / Gradle",
    "build.gradle.kts": "Kotlin / Gradle",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "Makefile": "Make",
    "style.css": "possible WordPress theme",
}
HARNESS_FILES = {
    "phpunit.xml": "PHPUnit", "phpunit.xml.dist": "PHPUnit",
    "pytest.ini": "pytest", "tox.ini": "tox", "conftest.py": "pytest",
    "jest.config.js": "Jest", "jest.config.ts": "Jest", "jest.config.mjs": "Jest",
    "vitest.config.ts": "Vitest", "vitest.config.js": "Vitest",
    "playwright.config.ts": "Playwright", "playwright.config.js": "Playwright",
    "cypress.config.js": "Cypress", "cypress.config.ts": "Cypress",
    "karma.conf.js": "Karma", ".rspec": "RSpec",
    "codeception.yml": "Codeception", "behat.yml": "Behat",
    "phpstan.neon": "PHPStan", "phpstan.neon.dist": "PHPStan",
    "phpcs.xml": "PHP_CodeSniffer", "phpcs.xml.dist": "PHP_CodeSniffer",
    ".eslintrc.json": "ESLint", "eslint.config.js": "ESLint",
    "k6.js": "k6", "lighthouserc.js": "Lighthouse CI", ".pa11yci": "pa11y",
}
FILE_ROUTE_HINTS = [
    (re.compile(r"(?:^|/)app/.*?/page\.(?:tsx|jsx|ts|js)$"), "Next.js app router page"),
    (re.compile(r"(?:^|/)app/.*?/route\.(?:ts|js)$"), "Next.js app router handler"),
    (re.compile(r"(?:^|/)pages/(?!api/).*\.(?:tsx|jsx|ts|js|vue)$"), "Next.js/Nuxt page"),
    (re.compile(r"(?:^|/)pages/api/.*\.(?:ts|js)$"), "Next.js API route"),
    (re.compile(r"(?:^|/)src/routes/.*\+(?:page|server)\.(?:svelte|ts|js)$"), "SvelteKit route"),
    (re.compile(r"(?:^|/)routes/.*\.(?:ts|js|php)$"), "routes directory entry"),
]


def should_scan(path: str) -> bool:
    name = os.path.basename(path)
    if SKIP_FILE_RE.search(name):
        return False
    ext = os.path.splitext(name)[1].lower()
    if name.startswith(".") and ext not in SCAN_EXT and name not in (".env", ".htaccess", ".pa11yci", ".rspec"):
        return False
    return ext in SCAN_EXT or name in STACK_FILES or name in HARNESS_FILES or name == ".htaccess"


def walk(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS
            and (not d.startswith(".") or d in KEEP_HIDDEN_DIRS)
        )
        for fn in sorted(filenames):
            yield os.path.join(dirpath, fn)


def scan(root: str, limit: int) -> dict:
    findings: dict[str, list] = {}
    stack: dict[str, str] = {}
    harness: dict[str, str] = {}
    file_routes: list[dict] = []
    counts: dict[str, int] = {}
    per_file: dict[tuple, int] = {}
    files_read = 0

    for full in walk(root):
        rel = os.path.relpath(full, root)
        name = os.path.basename(full)

        if name in STACK_FILES:
            stack.setdefault(STACK_FILES[name], rel)
        if name in HARNESS_FILES:
            harness.setdefault(HARNESS_FILES[name], rel)
        for pattern, label in FILE_ROUTE_HINTS:
            if pattern.search(rel.replace(os.sep, "/")):
                file_routes.append({"file": rel, "kind": label})
                break

        if not should_scan(full):
            continue
        try:
            if os.path.getsize(full) > MAX_BYTES:
                continue
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        files_read += 1

        for lineno, line in enumerate(lines, 1):
            if len(line) > 4000:
                line = line[:4000]
            for entry in PATTERNS:
                category, label, pattern = entry[0], entry[1], entry[2]
                only_in = entry[3] if len(entry) > 3 else None
                not_in = entry[4] if len(entry) > 4 else None
                if only_in and not only_in.search(name):
                    continue
                if not_in and not_in.search(name):
                    continue
                m = pattern.search(line)
                if not m:
                    continue
                counts[category] = counts.get(category, 0) + 1
                seen_key = (rel, category, label)
                per_file[seen_key] = per_file.get(seen_key, 0) + 1
                bucket = findings.setdefault(category, [])
                if len(bucket) < limit and per_file[seen_key] <= PER_FILE_CAP:
                    detail = next((g for g in m.groups() if g), "") if m.groups() else ""
                    bucket.append({
                        "file": rel,
                        "line": lineno,
                        "label": label,
                        "match": detail.strip()[:120] or m.group(0).strip()[:120],
                        "source": line.strip()[:200],
                    })

    return {
        "root": os.path.abspath(root),
        "files_scanned": files_read,
        "stack": stack,
        "test_harness": harness,
        "file_based_routes": file_routes[: limit * 2],
        "file_based_route_count": len(file_routes),
        "counts": counts,
        "findings": findings,
    }


CATEGORY_TITLES = [
    ("http_routes", "HTTP routes and request entry points"),
    ("api_specs", "API specifications"),
    ("ui_pages", "Pages and views"),
    ("cli_entrypoints", "CLI entry points"),
    ("scheduled_jobs", "Scheduled jobs, queues and workers"),
    ("webhooks_events", "Webhooks and event handlers"),
    ("auth_boundaries", "Authorization boundaries"),
    ("outbound_requests", "Outbound requests (SSRF candidates)"),
    ("file_uploads", "File upload handling"),
    ("raw_sql", "Raw SQL (injection candidates)"),
    ("possible_secrets", "Possible hardcoded secrets"),
]
CATEGORY_NOTES = {
    "auth_boundaries": "Each of these is a check that exists. The test is the surfaces that have none: compare against the route list above.",
    "outbound_requests": "Triage by hand — only the ones whose URL comes from request input are SSRF candidates.",
    "raw_sql": "Parameterised queries are fine; look for interpolation and for identifiers (table, column, ORDER BY) coming from input.",
    "possible_secrets": "Expect false positives from fixtures and examples. Verify before reporting, and never copy a live value into the report.",
}


def render(data: dict) -> str:
    out = [
        "# Surface inventory",
        "",
        f"`{data['root']}` — {data['files_scanned']} files scanned",
        "",
        "Generated by a pattern scan, so treat it as a starting point rather than a",
        "complete picture: dynamically registered routes and anything behind indirection",
        "will be missing. Confirm against the route table, the API spec and `--help`.",
        "",
    ]
    if data["stack"]:
        out += ["## Stack", ""]
        out += [f"- {k} — `{v}`" for k, v in sorted(data["stack"].items())] + [""]
    out += ["## Test harness present", ""]
    if data["test_harness"]:
        out += [f"- {k} — `{v}`" for k, v in sorted(data["test_harness"].items())]
        out += ["", "Match the suite you add to whichever of these is already in use.", ""]
    else:
        out += ["None detected. Pick the language's conventional runner and stay dependency-light.", ""]

    if data["file_based_routes"]:
        out += ["## File-based routes", "", f"{data['file_based_route_count']} found.", ""]
        out += [f"- `{r['file']}` — {r['kind']}" for r in data["file_based_routes"]]
        out += [""]

    out += ["## Summary", "", "| Category | Matches |", "|---|---|"]
    for key, title in CATEGORY_TITLES:
        n = data["counts"].get(key, 0)
        if n:
            out.append(f"| {title} | {n} |")
    out.append("")

    for key, title in CATEGORY_TITLES:
        rows = data["findings"].get(key)
        if not rows:
            continue
        total = data["counts"].get(key, len(rows))
        out += [f"## {title}", ""]
        if key in CATEGORY_NOTES:
            out += [CATEGORY_NOTES[key], ""]
        out += ["| Location | Kind | Match |", "|---|---|---|"]
        for r in rows:
            match = r["match"].replace("|", "\\|")
            out.append(f"| `{r['file']}:{r['line']}` | {r['label']} | `{match}` |")
        if total > len(rows):
            out.append("")
            out.append(f"…and {total - len(rows)} more. Raise `--limit` to see them all.")
        out.append("")

    out += [
        "## Next",
        "",
        "Tick surfaces off this list as you test them, and carry whatever is left into",
        "the report's **Not tested** section with a reason. Still to confirm by hand:",
        "the authoritative route table, the API spec, `--help` for every subcommand,",
        "exported library entry points, and which surfaces require which privileges.",
    ]
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="Inventory the surfaces a codebase exposes.")
    p.add_argument("root", nargs="?", default=".", help="project root (default: .)")
    p.add_argument("--out", metavar="PATH", help="write the report to a file as well as stdout")
    p.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    p.add_argument("--limit", type=int, default=40, help="max rows shown per category (default 40)")
    args = p.parse_args()

    if not os.path.isdir(args.root):
        print(f"error: {args.root} is not a directory", file=sys.stderr)
        return 2

    data = scan(args.root, args.limit)
    text = json.dumps(data, indent=2) if args.json else render(data)
    print(text)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        print(f"\nwritten to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
