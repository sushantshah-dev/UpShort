# Production Engineering — Holy Grail Checklist

This checklist is aligned with:
- Reliability Quest (incl. hidden checks)
- Scalability Quest
- Incident Response Quest

Goal: Max out all tiers + hidden score.

---

# 1. Reliability (Correctness + Resilience)

## 1.1 Input Validation
- [x] Validate URL format strictly
- [x] Reject missing required fields
- [ ] Enforce correct data types (no implicit coercion)
- [ ] Reject malformed JSON (invalid body / wrong content-type)
- [ ] Return structured JSON errors (no stack traces)

## 1.2 Data Integrity
- [x] Unique constraint on short codes
- [ ] Collision-safe ID generation (retry on conflict)
- [ ] Idempotent writes (no duplicates on retry)
- [ ] Consistent DB state under concurrent requests

## 1.3 Resource State Handling
- [x] Handle non-existent links → 404
- [x] Handle expired/disabled links → 404/410
- [x] Never redirect invalid/inactive resources

## 1.4 Error Handling
- [x] Global error handler (uniform response format)
- [ ] Clean error messages (JSON)
- [ ] No unhandled exceptions

## 1.5 Testing & CI
- [x] Unit tests (core logic)
- [ ] Integration tests (API → DB flow)
- [x] ≥70% coverage (pytest-cov)
- [x] CI pipeline blocks deploy on failure
- [ ] Tests cover edge cases (invalid input, duplicates)

## 1.6 Chaos / Failure
- [x] Kill container → auto restart (Docker restart policy)
- [x] App survives dependency failure (DB down → no crash)
- [ ] Garbage input → clean error response
- [ ] Document failure modes

---

# 2. Scalability (Load + Efficiency)

## 2.1 Load Testing
- [x] k6 / Locust setup
- [ ] Baseline: 50 concurrent users (record p95 latency)
- [ ] Scale: 200 concurrent users
- [ ] Target: 500+ users or ~100 req/sec
- [ ] Error rate < 5%

## 2.2 Horizontal Scaling
- [ ] Multiple app instances (Docker Compose)
- [x] Nginx load balancer in front
- [x] Stateless app design

## 2.3 Caching
- [x] Redis cache for reads
- [x] Cache hit avoids DB call
- [x] TTL configured
- [ ] Stale-While-Revalidate (SWR)
- [x] Cache invalidation on writes
- [ ] Cache warmup for hot keys
- [ ] Negative caching (404s)

## 2.4 Read Optimization
- [x] 3-tier fetch (memory → Redis → DB)
- [ ] Request coalescing (single-flight)
- [ ] TTL jitter (avoid stampede)

## 2.5 Load Protection
- [ ] Rate limiting (per IP)
- [ ] Adaptive rate limiting under load
- [ ] Load shedding (429 on overload)
- [ ] Retry budget (prevent retry storms)

## 2.6 Concurrency Control
- [ ] DB connection pooling
- [ ] Limit concurrent DB operations
- [ ] Prevent resource exhaustion

## 2.7 Bottleneck Analysis (Required)
- [ ] Identify slow component (DB / network / CPU)
- [ ] Apply fix (e.g., caching)
- [ ] Document before vs after impact

---

# 3. Incident Response (Observability + Ops)

## 3.1 Logging
- [ ] Structured JSON logs
- [ ] Include:
  - request_id
  - timestamp
  - endpoint
  - status
  - latency
- [ ] Log every request (including redirects)
- [ ] Log errors with classification (timeout, DB, rate limit)

## 3.2 Metrics
- [x] Expose `/metrics` endpoint (Prometheus)
- [x] Track:
  - request rate
  - error rate
  - latency (p50/p95)
  - cache hit/miss
  - retries
  - fallback usage

## 3.3 Alerts
- [ ] Alert on:
  - service down
  - high error rate
- [ ] Trigger within 5 minutes
- [ ] Send to channel (email / webhook / Discord)

## 3.4 Dashboard (Grafana)
- [x] Display:
  - latency
  - traffic
  - errors
  - saturation
- [x] Include cache + retry metrics
- [ ] Clearly show failure + recovery

## 3.5 Diagnosis Capability
- [ ] Correlate logs + metrics using request_id
- [ ] Identify root cause from dashboard

## 3.6 Runbook (Required for Gold)
- [ ] Document:
  - symptoms
  - detection
  - mitigation
  - recovery steps
- [ ] Example: DB down scenario

---

# 4. Hidden Checks (Critical)

## 4.1 Uniqueness
- [x] No duplicate short codes
- [ ] Collision handling implemented

## 4.2 Input Robustness
- [ ] Reject malformed JSON
- [ ] Reject wrong data types
- [x] Reject invalid URLs

## 4.3 Behavior Consistency
- [ ] Same error format across all endpoints
- [ ] Predictable responses under failure

## 4.4 Resource Validity
- [x] Disabled/expired links handled correctly
- [x] No unintended redirects

## 4.5 Observability Coverage
- [ ] All requests logged
- [ ] Failures clearly visible in logs + metrics

---

# 5. Demo Readiness

## 5.1 Normal Flow
- [x] Create short URL
- [x] Redirect works

## 5.2 Load
- [ ] Simulate 500+ users
- [ ] Show stable latency + low error rate

## 5.3 Cache Effect
- [ ] First request slower (DB)
- [ ] Subsequent requests faster (cache)

## 5.4 Failure Simulation
- [ ] Kill DB → system degrades gracefully
- [ ] No crashes

## 5.5 Recovery
- [ ] Restore DB → system auto-recovers

## 5.6 Observability
- [ ] Show Grafana dashboard
- [ ] Show logs for incident

---

# 6. Documentation (Bonus)

- [x] README (setup + run)
- [ ] Architecture diagram
- [x] API documentation
- [ ] Deployment guide
- [ ] Troubleshooting section
- [ ] Runbooks
- [ ] Decision log (why Redis, Nginx, etc.)
- [ ] Capacity estimate (users handled)

---

# Final Condition

You are done when:
- System does not crash under failure
- Behavior is consistent under bad input
- Load is handled with controlled degradation
- Failures are visible, explainable, and recoverable
