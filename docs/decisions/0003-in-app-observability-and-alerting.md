# ADR 0003: In-App Observability and Alerting

## Status

Accepted

## Context

The service needs enough operational visibility to diagnose deployment, dependency, and performance issues without introducing a large external observability platform footprint.

## Decision

Embed observability directly in the application and Compose stack:

- structured JSON logs from the Flask app
- rotating local log files plus stdout logging
- `/metrics` endpoint for Prometheus scraping
- `/health` endpoint with bootstrap, database, and cache status
- Prometheus alert rules for availability, latency, error rate, and host pressure
- Alertmanager forwarding through the local dispatcher to Discord

## Consequences

- Operators get immediate visibility with minimal moving parts.
- Health checks distinguish degraded cache state from hard database failures.
- Alert delivery depends on the dispatcher service and Discord webhook configuration.
- Local per-replica log files mean browser log viewing is replica-specific.

## Alternatives Considered

- Logs-only troubleshooting without metrics
- Third-party SaaS monitoring from the start

The current approach is intentionally lightweight and appropriate for the project’s stage.
