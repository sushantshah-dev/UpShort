# Runbook: Elevated 5xx Rate

## Trigger

- `Elevated5xxRate` alert fires
- Users report intermittent failures
- Logs show repeated `500` or `503` responses

## Impact

- A meaningful share of requests are failing across one or more routes.

## Immediate Checks

```bash
docker compose logs app --tail=300
curl -i http://localhost/health
```

In Prometheus, inspect:

- `upshort_http_requests_total`
- `upshort_http_request_latency_seconds`
- `upshort_fallback_usage_total`
- `upshort_bootstrap_attempts_total`

## Diagnosis

1. Separate `500` from `503` responses.
2. If failures cluster on authenticated routes, check PostgreSQL health first.
3. If failures cluster on redirects, check whether a code path is throwing after cache lookup.
4. If failures began after deploy, compare with the previous known-good release and consider rollback early.
5. If latency is rising before failures, inspect host CPU and memory pressure in Grafana or Prometheus.

## Remediation

- Fix the underlying dependency outage if PostgreSQL or Redis is unstable.
- Rebuild and redeploy if the release contains an application regression.
- Roll back if a safe forward fix is not immediate.
- Reduce traffic or replica count only if the database is the bottleneck and you need to stabilize quickly.

## Validation

Track recovery in Prometheus:

- 5xx ratio drops below alert threshold
- p95 latency returns to normal
- health endpoint returns healthy

Also validate with:

```bash
curl -f http://localhost/health
curl -I http://localhost/<known-working-slug>
```

## Follow-Up

- Identify the failing route pattern from structured logs.
- Document the root cause and add a regression test where possible.
