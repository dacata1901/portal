"""Part E HTTP load, latency percentile, fault-injection, and DB audit runner."""
import argparse
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db import audit, migrate, seed


def _percentile(sorted_values, pct):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return round(sorted_values[int(k)], 3)
    return round(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f), 3)


def _latency_summary(latencies):
    ordered = sorted(latencies)
    return {
        "count": len(ordered),
        "minMs": round(ordered[0], 3) if ordered else 0.0,
        "meanMs": round(statistics.fmean(ordered), 3) if ordered else 0.0,
        "p50Ms": _percentile(ordered, 50),
        "p95Ms": _percentile(ordered, 95),
        "p99Ms": _percentile(ordered, 99),
        "maxMs": round(ordered[-1], 3) if ordered else 0.0,
    }


def _http_json(url, method="GET", headers=None, payload=None, timeout=20):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
            return resp.status, dict(resp.headers), json.loads(raw), latency_ms
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        body = json.loads(raw) if raw else {}
        headers_out = dict(err.headers)
        err.close()
        return err.code, headers_out, body, latency_ms


def _start_server(db_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, PORTAL_DB=str(db_path), PORT=str(port), PORTAL_HOST="127.0.0.1", ENABLE_FAULTS="1")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "server.py")],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            status, _, body, _ = _http_json(f"{base_url}/healthz", timeout=1)
            if status == 200 and body.get("status") == "ok":
                return proc, base_url
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    proc.kill()
    proc.wait()
    raise RuntimeError("Server failed to start within timeout")


def run_benchmark(output_path):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "benchmark_e.sqlite3"
        migrate(str(db_path))
        seed(str(db_path))
        audit_before = audit(str(db_path))
        assert audit_before["ok"] and not audit_before["foreignKeys"], "Initial audit failed"

        proc, base_url = _start_server(db_path)
        try:
            # Workload E1: 100 concurrent HTTP registrations for 20-seat cloud-lab
            def register_student(idx):
                user_id = f"stu-{10001 + idx}"
                req_id = f"bench-e1-{user_id}"
                headers = {
                    "Content-Type": "application/json",
                    "Idempotency-Key": req_id,
                    "X-Demo-User": user_id,
                }
                status, resp_headers, body, latency_ms = _http_json(
                    f"{base_url}/api/events/cloud-lab/registrations",
                    method="POST",
                    headers=headers,
                    payload={"requestId": req_id},
                )
                return {
                    "userId": user_id,
                    "requestId": req_id,
                    "status": status,
                    "replayed": resp_headers.get("Idempotency-Replayed", "false"),
                    "latencyMs": latency_ms,
                    "code": body.get("code"),
                    "bookingId": (body.get("booking") or {}).get("id"),
                }

            with ThreadPoolExecutor(max_workers=32) as pool:
                e1_results = list(pool.map(register_student, range(100)))

            e1_201 = [r for r in e1_results if r["status"] == 201]
            e1_409 = [r for r in e1_results if r["status"] == 409 and r["code"] == "EVENT_FULL"]
            assert len(e1_201) == 20, f"Expected 20 HTTP 201, got {len(e1_201)}"
            assert len(e1_409) == 80, f"Expected 80 HTTP 409 EVENT_FULL, got {len(e1_409)}"

            # Workload E2: Drop-after-commit fault injection + 10x HTTP retry
            e2_key = "bench-e2-drop-ai-campus"
            drop_headers = {
                "Content-Type": "application/json",
                "Idempotency-Key": e2_key,
                "X-Demo-User": "stu-10001",
                "X-Drop-After-Commit": "1",
            }
            dropped = False
            drop_error = None
            try:
                _http_json(
                    f"{base_url}/api/events/ai-campus/registrations",
                    method="POST",
                    headers=drop_headers,
                    payload={"requestId": e2_key},
                )
            except Exception as exc:
                dropped = True
                drop_error = type(exc).__name__
            assert dropped, "Expected X-Drop-After-Commit to drop HTTP connection"

            retry_headers = {
                "Content-Type": "application/json",
                "Idempotency-Key": e2_key,
                "X-Demo-User": "stu-10001",
            }
            e2_retries = []
            for _ in range(10):
                status, resp_headers, body, latency_ms = _http_json(
                    f"{base_url}/api/events/ai-campus/registrations",
                    method="POST",
                    headers=retry_headers,
                    payload={"requestId": e2_key},
                )
                e2_retries.append(
                    {
                        "status": status,
                        "replayed": resp_headers.get("Idempotency-Replayed"),
                        "latencyMs": latency_ms,
                        "bookingId": (body.get("booking") or {}).get("id"),
                        "remainingCapacity": body.get("remainingCapacity"),
                    }
                )
            booking_ids = {r["bookingId"] for r in e2_retries}
            assert all(r["status"] == 201 and r["replayed"] == "true" for r in e2_retries), "Replay assertion failed"
            assert len(booking_ids) == 1 and None not in booking_ids, "Expected single booking ID across retries"
            assert all(r["remainingCapacity"] == 33 for r in e2_retries), "Expected ai-campus remainingCapacity == 33"
            target_booking_id = next(iter(booking_ids))

            _, _, ai_event_after_e2, _ = _http_json(f"{base_url}/api/events/ai-campus")
            assert ai_event_after_e2["remainingCapacity"] == 33, "GET ai-campus remainingCapacity mismatch after E2"

            # Workload E3: 20 concurrent cancellations + idempotency conflict check
            def cancel_concurrent(idx):
                cancel_key = f"bench-e3-cancel-{idx}"
                headers = {
                    "Content-Type": "application/json",
                    "Idempotency-Key": cancel_key,
                    "X-Demo-User": "stu-10001",
                }
                status, resp_headers, body, latency_ms = _http_json(
                    f"{base_url}/api/registrations/{target_booking_id}/cancel",
                    method="POST",
                    headers=headers,
                    payload={"requestId": cancel_key},
                )
                return {
                    "status": status,
                    "bookingStatus": (body.get("booking") or {}).get("status"),
                    "remainingCapacity": body.get("remainingCapacity"),
                    "latencyMs": latency_ms,
                }

            with ThreadPoolExecutor(max_workers=20) as pool:
                e3_cancels = list(pool.map(cancel_concurrent, range(20)))

            assert all(r["status"] == 200 and r["bookingStatus"] == "cancelled" for r in e3_cancels)
            _, _, ai_event_after_e3, _ = _http_json(f"{base_url}/api/events/ai-campus")
            assert ai_event_after_e3["remainingCapacity"] == 34, "Expected ai-campus remainingCapacity == 34 after cancel"

            conflict_status, _, conflict_body, conflict_latency = _http_json(
                f"{base_url}/api/events/career-kit/registrations",
                method="POST",
                headers=retry_headers,
                payload={"requestId": e2_key},
            )
            assert conflict_status == 409 and conflict_body.get("code") == "IDEMPOTENCY_CONFLICT"
        finally:
            proc.terminate()
            proc.wait(timeout=10)

        audit_after = audit(str(db_path))
        assert audit_after["ok"] and not audit_after["foreignKeys"], "Final DB audit failed"

        report = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "ok": True,
            "auditBefore": audit_before,
            "auditAfter": audit_after,
            "workloadE1": {
                "description": "100 concurrent HTTP registrations for 20-seat cloud-lab",
                "http201Count": len(e1_201),
                "http409EventFullCount": len(e1_409),
                "latency": _latency_summary([r["latencyMs"] for r in e1_results]),
                "samples": e1_results[:5],
            },
            "workloadE2": {
                "description": "Drop-after-commit fault injection followed by 10 HTTP retries",
                "faultInjected": dropped,
                "faultException": drop_error,
                "retryCount": len(e2_retries),
                "bookingId": target_booking_id,
                "allHttp201": all(r["status"] == 201 for r in e2_retries),
                "allReplayedHeaderTrue": all(r["replayed"] == "true" for r in e2_retries),
                "remainingCapacityAfterE2": ai_event_after_e2["remainingCapacity"],
                "latency": _latency_summary([r["latencyMs"] for r in e2_retries]),
            },
            "workloadE3": {
                "description": "20 concurrent cancellations + idempotency conflict verification",
                "cancelCount": len(e3_cancels),
                "allHttp200": all(r["status"] == 200 for r in e3_cancels),
                "remainingCapacityAfterCancel": ai_event_after_e3["remainingCapacity"],
                "conflictStatus": conflict_status,
                "conflictCode": conflict_body.get("code"),
                "conflictLatencyMs": conflict_latency,
                "cancelLatency": _latency_summary([r["latencyMs"] for r in e3_cancels]),
            },
        }
        out = Path(output_path)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report


def main():
    parser = argparse.ArgumentParser(description="Run Part E HTTP benchmark & fault drill.")
    parser.add_argument("--output", default=str(ROOT / "BENCHMARK-E-RESULTS.json"))
    args = parser.parse_args()
    report = run_benchmark(args.output)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "output": str(args.output),
                "e1_201": report["workloadE1"]["http201Count"],
                "e1_409": report["workloadE1"]["http409EventFullCount"],
                "e1_p50_ms": report["workloadE1"]["latency"]["p50Ms"],
                "e1_p95_ms": report["workloadE1"]["latency"]["p95Ms"],
                "e1_p99_ms": report["workloadE1"]["latency"]["p99Ms"],
                "e2_replayed_all": report["workloadE2"]["allReplayedHeaderTrue"],
                "e3_conflict": report["workloadE3"]["conflictStatus"],
                "audit_ok": report["auditAfter"]["ok"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
