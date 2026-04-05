# Runbook: Database Unavailable

## Trigger

- `/health` returns `503` with a failing database check
- Redirect analytics stop persisting
- CRUD routes return `503`
- `BootstrapFailuresDetected` alert fires

## Impact

- New sessions and CRUD operations may fail.
- Redirects may still resolve from cache, but analytics can fall back to cache-only increments.
- Seed/bootstrap completion may be blocked during startup.

## Immediate Checks

```bash
docker compose ps db
docker compose logs db --tail=200
docker compose logs app --tail=200
```

## Diagnosis

1. Confirm PostgreSQL is running and healthy.
2. Verify credentials and host settings:

```bash
grep '^DATABASE_' .env
```

3. Check whether connection pool limits are too low for the active replica count.
4. Look for sequence, table creation, or migration-related errors in app logs.
5. If this started after a deploy, compare the new code path with the previous release.

## Remediation

- Restart PostgreSQL if it is hung or not accepting connections.
- Fix invalid `DATABASE_*` values and redeploy.
- Reduce app replica count or increase database capacity if the issue is saturation.
- If the failure started after release and no quick fix exists, roll back the app deployment.

## Validation

```bash
curl http://localhost/health
```

Healthy result should show:

- `"state": "ok"` or `"state": "degraded"` only when Redis is the remaining issue
- database check with `"status": "ok"`

Then verify:

```bash
curl -i http://localhost/
```

And create a test URL through the UI or JSON endpoint.

## Notes

- The app auto-creates tables and adds some columns at startup, but it does not support schema rollback.
- Cached redirects can hide partial database outages from end users, so always check metrics and health, not just redirect success.
