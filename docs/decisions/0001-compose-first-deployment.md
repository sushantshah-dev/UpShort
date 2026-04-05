# ADR 0001: Compose-First Deployment

## Status

Accepted

## Context

The project needs a deployment topology that is easy to run locally, easy to demo, and simple for a small team to operate without dedicated platform tooling.

## Decision

Use Docker Compose as the primary deployment model, with services for:

- `app`
- `nginx`
- `db`
- `redis`
- `prometheus`
- `alertmanager`
- `alert-dispatcher`
- `node-exporter`
- `grafana`

Nginx is the only app-facing public entrypoint. The Flask app can run with multiple replicas behind the proxy.

## Consequences

- Local development and production-like testing share the same topology.
- Operators can scale the app tier without introducing an orchestrator.
- Rollbacks are straightforward redeploys but remain largely manual.
- Service discovery and availability assumptions are limited to a single Compose network.

## Alternatives Considered

- Running Flask directly on a host without containers
- Kubernetes-based deployment

Compose was chosen because it matches the project’s current complexity and operational footprint.
