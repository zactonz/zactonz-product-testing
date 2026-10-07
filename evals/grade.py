#!/usr/bin/env python3
"""Score each run's recall against the planted defects.

A hit requires the defect's surface AND its mechanism in the same report, so a
vague "validation could be improved" does not count as having found D3.
"""
import pathlib, re, sys

DEFECTS = {
    "D1": ("IDOR on /invoices/<id>", [r"/invoices"], [r"\bidor\b", r"ownership", r"other (?:user|account)", r"bob'?s invoice", r"broken (?:object|access)", r"authoriz\w+ (?:check|bypass|missing)", r"cross-?account"]),
    "D2": ("Mass assignment on PATCH /me", [r"/me\b", r"\bpatch\b"], [r"mass ?assignment", r"is_admin", r"privilege escalat", r"arbitrary (?:field|column)"]),
    "D3": ("Negative limit bypasses LIMIT", [r"/items", r"\blimit\b"], [r"negative", r"limit=-1"]),
    "D4": ("SQL injection via sort", [r"/items", r"\bsort\b", r"order by"], [r"sql ?inject", r"\bsqli\b", r"interpolat", r"injection"]),
    "D5": ("Reflected XSS on /search", [r"/search"], [r"\bxss\b", r"cross-?site scripting", r"unescaped", r"not escaped", r"html ?escap"]),
    "D6": ("SSRF on /preview", [r"/preview"], [r"\bssrf\b", r"server-?side request forgery", r"loopback", r"internal (?:url|address|network)", r"169\.254", r"metadata"]),
    "D7": ("500 + stack trace on malformed JSON", [r"malformed", r"invalid json", r"bad json"], [r"stack ?trace", r"traceback", r"should (?:be|return) (?:a )?400", r"\b400\b", r"debug"]),
    "D8": ("Quota race on POST /jobs", [r"/jobs", r"quota"], [r"race", r"concurren\w+", r"read-?then-?write", r"atomic", r"overshoot", r"exceed\w* the quota", r"more than 3"]),
    "D9": ("Byte truncation splits multibyte chars", [r"/profile", r"truncat"], [r"\bbyte", r"multibyte", r"unicode", r"emoji", r"surrogate", r"utf-?8"]),
    "D10": ("UI defects on /app", [r"/app\b"], [r"label", r"outline", r"focus", r"overflow", r"dark mode", r"console (?:error|typeerror)", r"ledgerinit", r"contrast", r"accessib"]),
}


def score(path):
    files = [f for pat in ("*.md", "*.txt", "*.json", "*.sh", "*.py") for f in path.rglob(pat) if f.is_file()]
    blob = "\n".join(f.read_text(errors="ignore") for f in files)
    low = blob.lower()
    hits = {}
    for did, (label, surfaces, mechs) in DEFECTS.items():
        hits[did] = any(re.search(p, low) for p in surfaces) and any(re.search(p, low) for p in mechs)
    return hits, len(blob), len(files)


base = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
runs = {}
for name in ("with_skill", "without_skill"):
    d = base / name
    runs[name] = score(d) if d.exists() else ({k: False for k in DEFECTS}, 0, 0)

print(f"{'':6} {'planted defect':46} with skill   baseline")
print("-" * 78)
for did, (label, *_r) in DEFECTS.items():
    a = " FOUND " if runs["with_skill"][0][did] else "   -   "
    b = "FOUND" if runs["without_skill"][0][did] else "  -  "
    print(f"{did:6} {label:46} {a}      {b}")
print("-" * 78)
for name in ("with_skill", "without_skill"):
    hits, size, nfiles = runs[name]
    n = sum(hits.values())
    print(f"{name:16} {n}/{len(DEFECTS)} found · {nfiles} files · {size:,} chars of report + evidence")
