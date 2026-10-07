#!/usr/bin/env python3
"""Concurrent HTTP load generator using only the Python standard library.

Exists because k6, wrk, hey and vegeta are usually not installed, and ApacheBench
reports no usable percentiles. Produces latency percentiles, a status histogram and
classified errors, and can act as a CI gate via --fail-over-errors / --fail-over-p95.

Non-local targets require --allow-remote, so that pointing load at a remote host is
a deliberate act rather than a typo. A load test is indistinguishable from a
denial-of-service attempt: only run it against hosts you own or are authorized to
test, and agree a ceiling before touching anything live.
"""

from __future__ import annotations

import argparse
import csv
import http.client
import json
import socket
import ssl
import sys
import threading
import time
from urllib.parse import urlsplit

LOCAL_SUFFIXES = (".localhost", ".test")
LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "0"}


def is_local(host: str) -> bool:
    h = (host or "").strip("[]").lower()
    return h in LOCAL_NAMES or h.startswith("127.") or h.endswith(LOCAL_SUFFIXES)


def classify(exc: BaseException) -> str:
    """Map an exception to a short error class, so the summary groups causes."""
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(exc, ConnectionResetError):
        return "connection_reset"
    if isinstance(exc, BrokenPipeError):
        return "broken_pipe"
    if isinstance(exc, socket.gaierror):
        return "dns_failure"
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "tls_cert_invalid"
    if isinstance(exc, ssl.SSLError):
        return "tls_error"
    if isinstance(exc, http.client.HTTPException):
        return "protocol_error"
    if isinstance(exc, OSError):
        return f"os_error_{exc.errno}"
    return type(exc).__name__


def percentile(ordered: list[float], p: float) -> float:
    if not ordered:
        return 0.0
    k = (len(ordered) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


class Pacer:
    """Shared run state: request budget, deadline and optional arrival-rate cap."""

    def __init__(self, budget: int | None, deadline: float | None, rps: float | None):
        self._lock = threading.Lock()
        self._budget = budget
        self.deadline = deadline
        self.rps = rps
        self._next_slot = time.monotonic()
        self.stop = threading.Event()

    def claim(self) -> bool:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            return False
        if self._budget is None:
            return not self.stop.is_set()
        with self._lock:
            if self._budget <= 0:
                return False
            self._budget -= 1
        return not self.stop.is_set()

    def wait_slot(self) -> None:
        if not self.rps:
            return
        with self._lock:
            slot = max(self._next_slot, time.monotonic())
            self._next_slot = slot + 1.0 / self.rps
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def connect(parts, timeout: float, insecure: bool):
    port = parts.port
    if parts.scheme == "https":
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return http.client.HTTPSConnection(parts.hostname, port or 443, timeout=timeout, context=ctx)
    return http.client.HTTPConnection(parts.hostname, port or 80, timeout=timeout)


def worker(index: int, args, parts, path: str, headers: dict, body, pacer: Pacer, sink: list, t_zero: float):
    if args.ramp:
        time.sleep(args.ramp * index / max(args.concurrency, 1))

    conn = None
    while pacer.claim():
        pacer.wait_slot()
        if conn is None:
            try:
                conn = connect(parts, args.timeout, args.insecure)
            except Exception as exc:  # connection setup is itself a result worth recording
                sink.append((time.monotonic() - t_zero, 0.0, None, classify(exc), 0))
                conn = None
                time.sleep(0.05)
                continue

        offset = time.monotonic() - t_zero
        started = time.monotonic()
        try:
            conn.request(args.method, path, body=body, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()  # must drain the body to reuse the connection
            sink.append((offset, time.monotonic() - started, resp.status, None, len(payload)))
            if resp.will_close:
                conn.close()
                conn = None
        except Exception as exc:
            sink.append((offset, time.monotonic() - started, None, classify(exc), 0))
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            conn = None

        if args.think:
            time.sleep(args.think)

    if conn:
        try:
            conn.close()
        except Exception:
            pass


def summarise(records: list, args, elapsed: float) -> dict:
    kept = [r for r in records if r[0] >= args.warmup]
    discarded = len(records) - len(kept)

    ok_codes = set(args.expect_status) if args.expect_status else None

    def accepted(status):
        if status is None:
            return False
        return status in ok_codes if ok_codes else status < 400

    statuses: dict[str, int] = {}
    errors: dict[str, int] = {}
    ok_latencies: list[float] = []
    all_latencies: list[float] = []
    bytes_total = 0

    for _offset, latency, status, err, size in kept:
        all_latencies.append(latency)
        if err:
            errors[err] = errors.get(err, 0) + 1
            continue
        statuses[str(status)] = statuses.get(str(status), 0) + 1
        bytes_total += size
        if accepted(status):
            ok_latencies.append(latency)
        else:
            key = f"unexpected_status_{status}"
            errors[key] = errors.get(key, 0) + 1

    ok_latencies.sort()
    all_latencies.sort()
    failures = sum(errors.values())
    measured = max(elapsed - args.warmup, 1e-9)

    def lat(ordered):
        if not ordered:
            return {k: None for k in ("min", "mean", "p50", "p75", "p90", "p95", "p99", "max")}
        return {
            "min": ordered[0] * 1000,
            "mean": sum(ordered) / len(ordered) * 1000,
            "p50": percentile(ordered, 50) * 1000,
            "p75": percentile(ordered, 75) * 1000,
            "p90": percentile(ordered, 90) * 1000,
            "p95": percentile(ordered, 95) * 1000,
            "p99": percentile(ordered, 99) * 1000,
            "max": ordered[-1] * 1000,
        }

    buckets: dict[int, dict] = {}
    for offset, latency, status, err, _size in kept:
        slot = int(offset - args.warmup)
        b = buckets.setdefault(slot, {"n": 0, "errors": 0, "lat": []})
        b["n"] += 1
        if err or not accepted(status):
            b["errors"] += 1
        else:
            b["lat"].append(latency)

    timeline = []
    for slot in sorted(buckets):
        b = buckets[slot]
        b["lat"].sort()
        timeline.append({
            "second": slot,
            "requests": b["n"],
            "errors": b["errors"],
            "p95_ms": percentile(b["lat"], 95) * 1000 if b["lat"] else None,
        })

    return {
        "target": args.url,
        "method": args.method,
        "concurrency": args.concurrency,
        "ramp_seconds": args.ramp,
        "rps_cap": args.rps,
        "think_seconds": args.think,
        "warmup_seconds": args.warmup,
        "wall_seconds": round(elapsed, 3),
        "measured_seconds": round(measured, 3),
        "requests": len(kept),
        "discarded_warmup": discarded,
        "successful": len(ok_latencies),
        "failed": failures,
        "error_rate_pct": round(failures / len(kept) * 100, 3) if kept else 0.0,
        "throughput_rps": round(len(kept) / measured, 2),
        "bytes_received": bytes_total,
        "status_counts": dict(sorted(statuses.items())),
        "error_counts": dict(sorted(errors.items(), key=lambda kv: -kv[1])),
        "latency_ms_successful": lat(ok_latencies),
        "latency_ms_all": lat(all_latencies),
        "timeline": timeline,
    }


def render(s: dict) -> str:
    def ms(v):
        return "—" if v is None else f"{v:.1f}ms"

    lines = [
        "",
        f"  {s['method']} {s['target']}",
        f"  concurrency {s['concurrency']}"
        + (f" · ramp {s['ramp_seconds']}s" if s["ramp_seconds"] else "")
        + (f" · rps cap {s['rps_cap']}" if s["rps_cap"] else "")
        + (f" · think {s['think_seconds']}s" if s["think_seconds"] else "")
        + (f" · warmup discarded {s['warmup_seconds']}s" if s["warmup_seconds"] else ""),
        "",
        f"  requests      {s['requests']}  ({s['successful']} ok, {s['failed']} failed = {s['error_rate_pct']}%)",
        f"  duration      {s['measured_seconds']}s measured",
        f"  throughput    {s['throughput_rps']} req/s",
        f"  received      {s['bytes_received']:,} bytes",
        "",
        "  latency (successful responses)",
    ]
    L = s["latency_ms_successful"]
    lines += [
        f"    min {ms(L['min'])}   mean {ms(L['mean'])}   max {ms(L['max'])}",
        f"    p50 {ms(L['p50'])}   p75 {ms(L['p75'])}   p90 {ms(L['p90'])}   p95 {ms(L['p95'])}   p99 {ms(L['p99'])}",
        "",
    ]
    if s["status_counts"]:
        lines.append("  status codes")
        for code, n in s["status_counts"].items():
            lines.append(f"    {code}  {n}")
        lines.append("")
    if s["error_counts"]:
        lines.append("  errors")
        for name, n in s["error_counts"].items():
            lines.append(f"    {name}  {n}")
        lines.append("")
    tl = s["timeline"]
    if len(tl) > 1:
        lines.append("  per second (second · requests · errors · p95)")
        shown = tl if len(tl) <= 20 else tl[:10] + [None] + tl[-9:]
        for row in shown:
            if row is None:
                lines.append(f"    … {len(tl) - 19} more seconds …")
                continue
            lines.append(
                f"    {row['second']:>4}  {row['requests']:>6}  {row['errors']:>6}  {ms(row['p95_ms'])}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Concurrent HTTP load generator (standard library only).",
        epilog="Only run against hosts you own or are authorized to test.",
    )
    p.add_argument("url")
    p.add_argument("-c", "--concurrency", type=int, default=10, help="concurrent workers (default 10)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("-n", "--requests", type=int, help="total requests to send")
    g.add_argument("-d", "--duration", type=float, help="seconds to sustain traffic")
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("-H", "--header", action="append", default=[], metavar="'K: V'")
    p.add_argument("-b", "--body", help="request body, or @path to read from a file")
    p.add_argument("--rps", type=float, help="cap total arrival rate, modelling real traffic rather than a closed loop")
    p.add_argument("--ramp", type=float, default=0.0, metavar="SEC", help="stagger worker start over this period")
    p.add_argument("--think", type=float, default=0.0, metavar="SEC", help="pause between a worker's requests")
    p.add_argument("--warmup", type=float, default=0.0, metavar="SEC", help="discard results from the first N seconds")
    p.add_argument("--timeout", type=float, default=10.0, help="per-request timeout (default 10)")
    p.add_argument("--expect-status", metavar="LIST", help="comma-separated codes to treat as success (default: any <400)")
    p.add_argument("--insecure", action="store_true", help="skip TLS verification")
    p.add_argument("--allow-remote", action="store_true", help="required to target a non-local host")
    p.add_argument("--json", metavar="PATH", help="write the full summary as JSON")
    p.add_argument("--csv", metavar="PATH", help="write per-request records as CSV")
    p.add_argument("--fail-over-errors", type=float, metavar="PCT", help="exit 1 if the error rate exceeds this")
    p.add_argument("--fail-over-p95", type=float, metavar="MS", help="exit 1 if p95 exceeds this")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress progress output")
    args = p.parse_args()

    if not args.requests and not args.duration:
        args.requests = 200

    parts = urlsplit(args.url if "://" in args.url else "http://" + args.url)
    if not parts.hostname:
        print("error: could not parse a host from the URL", file=sys.stderr)
        return 2
    if not is_local(parts.hostname) and not args.allow_remote:
        print(
            f"refusing to load-test {parts.hostname}: not a local host.\n"
            "Pass --allow-remote only for a host you own or are authorized to test,\n"
            "and agree a concurrency and duration ceiling first if it is live.",
            file=sys.stderr,
        )
        return 2

    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query

    headers = {"Host": parts.netloc, "User-Agent": "product-testing-loadtest/1.0", "Accept": "*/*"}
    for raw in args.header:
        if ":" not in raw:
            print(f"error: header {raw!r} is not 'Key: Value'", file=sys.stderr)
            return 2
        k, v = raw.split(":", 1)
        headers[k.strip()] = v.strip()

    body = args.body
    if body and body.startswith("@"):
        with open(body[1:], "rb") as fh:
            body = fh.read()
    elif body:
        body = body.encode()
    if body is not None:
        headers.setdefault("Content-Length", str(len(body)))

    args.expect_status = [int(x) for x in args.expect_status.split(",")] if args.expect_status else None

    sinks = [[] for _ in range(args.concurrency)]
    t_zero = time.monotonic()
    deadline = t_zero + args.ramp + args.duration if args.duration else None
    pacer = Pacer(args.requests, deadline, args.rps)

    threads = [
        threading.Thread(
            target=worker,
            args=(i, args, parts, path, headers, body, pacer, sinks[i], t_zero),
            daemon=True,
        )
        for i in range(args.concurrency)
    ]
    for t in threads:
        t.start()

    try:
        last = 0
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
            if not args.quiet:
                done = sum(len(s) for s in sinks)
                if done != last:
                    print(f"\r  {done} requests, {time.monotonic() - t_zero:.0f}s elapsed…", end="", file=sys.stderr)
                    last = done
    except KeyboardInterrupt:
        pacer.stop.set()
        print("\n  interrupted; summarising what completed", file=sys.stderr)

    pacer.stop.set()
    for t in threads:
        t.join(timeout=args.timeout + 2)
    elapsed = time.monotonic() - t_zero
    if not args.quiet:
        print("\r" + " " * 60 + "\r", end="", file=sys.stderr)

    records = sorted((r for sink in sinks for r in sink), key=lambda r: r[0])
    if not records:
        print("no requests completed — is the target up?", file=sys.stderr)
        return 2

    summary = summarise(records, args, elapsed)
    print(render(summary))

    # A run that measured nothing, or in which nothing succeeded, must not read as a
    # pass. Silent zeros are how load results get misquoted as capacity.
    if summary["requests"] == 0:
        print(f"  WARNING: every result fell inside --warmup {args.warmup}s, so nothing was measured.", file=sys.stderr)
    elif summary["successful"] == 0:
        print("  WARNING: no request succeeded — this measures failure, not capacity.", file=sys.stderr)

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(summary, fh, indent=2)
        print(f"  summary written to {args.json}")
    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["offset_s", "latency_ms", "status", "error", "bytes"])
            for offset, latency, status, err, size in records:
                w.writerow([f"{offset:.4f}", f"{latency * 1000:.3f}", status or "", err or "", size])
        print(f"  per-request records written to {args.csv}")

    breached = []
    if args.fail_over_errors is not None and summary["error_rate_pct"] > args.fail_over_errors:
        breached.append(f"error rate {summary['error_rate_pct']}% > {args.fail_over_errors}%")
    p95 = summary["latency_ms_successful"]["p95"]
    if args.fail_over_p95 is not None and p95 is not None and p95 > args.fail_over_p95:
        breached.append(f"p95 {p95:.1f}ms > {args.fail_over_p95}ms")
    if breached:
        print("\n  THRESHOLD BREACHED: " + "; ".join(breached), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
