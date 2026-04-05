# ADR 0002: Cache-First Redirect Path

## Status

Accepted

## Context

Public redirects are the highest-frequency request path in the system. Hitting PostgreSQL on every redirect would add avoidable latency and increase database load.

## Decision

Resolve redirects through a three-step lookup order:

1. per-process in-memory cache
2. shared Redis cache
3. PostgreSQL

On database reads, the app repopulates both cache tiers. Redis is treated as optional for health: the application can degrade instead of fail hard when Redis is unavailable.

## Consequences

- Common redirects are faster and cheaper to serve.
- The system tolerates Redis outages with degraded behavior.
- Cache coherence is best-effort and depends on explicit delete/update calls.
- During database outages, some cached redirects can continue to resolve while write-heavy analytics degrade.

## Alternatives Considered

- Database-only redirect resolution
- Redis-only caching without local memory

The chosen design balances latency, resilience, and implementation simplicity.
