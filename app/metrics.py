from __future__ import annotations

import time

from flask import Response, g, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

HTTP_REQUESTS_TOTAL = Counter(
    "upshort_http_requests_total",
    "Total HTTP requests handled by the Flask app.",
    ["method", "path", "status"],
)
HTTP_REQUEST_LATENCY_SECONDS = Histogram(
    "upshort_http_request_latency_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "upshort_http_requests_in_progress",
    "HTTP requests currently being processed.",
)
CACHE_OPERATIONS_TOTAL = Counter(
    "upshort_cache_operations_total",
    "Cache lookups and mutations grouped by backend and outcome.",
    ["operation", "backend", "result"],
)
FALLBACK_USAGE_TOTAL = Counter(
    "upshort_fallback_usage_total",
    "Fallback code paths used when preferred dependencies are unavailable.",
    ["operation"],
)
BOOTSTRAP_ATTEMPTS_TOTAL = Counter(
    "upshort_bootstrap_attempts_total",
    "Database bootstrap attempts grouped by result.",
    ["result"],
)
BOOTSTRAP_RETRIES_TOTAL = Counter(
    "upshort_bootstrap_retries_total",
    "Database bootstrap retries attempted after startup.",
)
PROCESS_CPU_USAGE_PERCENT = Gauge(
    "upshort_process_cpu_usage_percent",
    "Approximate CPU usage of the Flask process since the previous metrics scrape.",
)
PROCESS_RESIDENT_MEMORY_BYTES = Gauge(
    "upshort_process_resident_memory_bytes",
    "Resident memory currently used by the Flask process in bytes.",
)

_PROCESS_CPU_STATE = {
    "cpu_time": None,
    "monotonic_time": None,
}


def _request_path_label() -> str:
    rule = request.url_rule.rule if request.url_rule is not None else request.path
    return rule or "unknown"


def record_cache_lookup(source: str, result: str) -> None:
    CACHE_OPERATIONS_TOTAL.labels(
        operation="lookup",
        backend=source,
        result=result,
    ).inc()


def record_cache_write(backend: str, result: str = "success") -> None:
    CACHE_OPERATIONS_TOTAL.labels(
        operation="write",
        backend=backend,
        result=result,
    ).inc()


def record_cache_delete(backend: str, result: str = "success") -> None:
    CACHE_OPERATIONS_TOTAL.labels(
        operation="delete",
        backend=backend,
        result=result,
    ).inc()


def record_fallback_usage(operation: str) -> None:
    FALLBACK_USAGE_TOTAL.labels(operation=operation).inc()


def record_bootstrap_attempt(result: str) -> None:
    BOOTSTRAP_ATTEMPTS_TOTAL.labels(result=result).inc()


def record_bootstrap_retry() -> None:
    BOOTSTRAP_RETRIES_TOTAL.inc()


def _collect_process_cpu_percent() -> float:
    cpu_time = time.process_time()
    monotonic_time = time.perf_counter()
    previous_cpu_time = _PROCESS_CPU_STATE["cpu_time"]
    previous_monotonic_time = _PROCESS_CPU_STATE["monotonic_time"]
    _PROCESS_CPU_STATE["cpu_time"] = cpu_time
    _PROCESS_CPU_STATE["monotonic_time"] = monotonic_time

    if previous_cpu_time is None or previous_monotonic_time is None:
        return 0.0

    elapsed = monotonic_time - previous_monotonic_time
    if elapsed <= 0:
        return 0.0

    cpu_delta = max(cpu_time - previous_cpu_time, 0.0)
    return (cpu_delta / elapsed) * 100.0


def _collect_process_resident_memory_bytes() -> int:
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1]) * 1024
    except OSError:
        pass
    return 0


def _update_process_metrics() -> None:
    PROCESS_CPU_USAGE_PERCENT.set(_collect_process_cpu_percent())
    PROCESS_RESIDENT_MEMORY_BYTES.set(_collect_process_resident_memory_bytes())


def instrument_app(app) -> None:
    if app.extensions.get("upshort_metrics_instrumented"):
        return

    @app.before_request
    def _start_metrics_timer():
        if request.path == "/metrics":
            g._metrics_in_progress = False
            return

        g._metrics_started_at = time.perf_counter()
        g._metrics_in_progress = True
        HTTP_REQUESTS_IN_PROGRESS.inc()

    @app.after_request
    def _observe_request_metrics(response):
        if getattr(g, "_metrics_in_progress", False):
            path = _request_path_label()
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                path=path,
                status=str(response.status_code),
            ).inc()
            HTTP_REQUEST_LATENCY_SECONDS.labels(
                method=request.method,
                path=path,
            ).observe(time.perf_counter() - g._metrics_started_at)
            HTTP_REQUESTS_IN_PROGRESS.dec()
            g._metrics_in_progress = False

        return response

    @app.teardown_request
    def _cleanup_metrics(_exc):
        if getattr(g, "_metrics_in_progress", False):
            HTTP_REQUESTS_IN_PROGRESS.dec()
            g._metrics_in_progress = False

    @app.route("/metrics")
    def metrics():
        _update_process_metrics()
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    app.extensions["upshort_metrics_instrumented"] = True
