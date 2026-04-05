# Runbook: App Target Down

## Trigger

- `AppTargetDown` alert fires
- `/health` fails through Nginx
- Prometheus target for `upshort-app` is down

## Impact

- Auth flows, dashboard access, URL CRUD, redirect freshness, and metrics scraping may fail.
- Existing cached redirects may still work only if at least one app replica is reachable.

## Immediate Checks

```bash
docker compose ps
docker compose ps app
docker compose logs app --tail=200
curl -i http://localhost/health
```

## Diagnosis

1. If no `app` containers are running, restart the service:

```bash
docker compose up -d app
```

2. If containers are restarting, inspect startup errors:

- database authentication failures
- schema/bootstrap errors
- missing environment variables
- import or syntax errors

3. If app containers are healthy but Nginx is failing, inspect:

```bash
docker compose logs nginx --tail=200
```

4. If only some replicas are unhealthy, compare logs across the app service and confirm shared dependencies are stable.

## Remediation

- Fix bad environment values in `.env` and redeploy with `docker compose up --build -d`.
- Restore PostgreSQL or Redis connectivity if the app depends on them during startup.
- If the current release is faulty, roll back to a known-good commit and redeploy.

## Validation

```bash
curl -f http://localhost/health
curl -f http://localhost/metrics >/dev/null
```

- Confirm `upshort-app` is healthy in Prometheus targets.
- Confirm login page and a sample redirect both work.

## Follow-Up

- Capture the failing logs.
- Record whether this was an app regression, dependency outage, or deployment issue.
- Add or update a test if the outage was caused by an application regression.
