# M7 Task 17 — Observability, security hardening, and recovery

## Scope

Implement only FRE-21 / Task 17 on top of `main@2e84e21`. PostgreSQL remains the
authoritative store; Redis and Celery are recoverable delivery/coordination layers. No live trading,
automatic policy activation, or Task 18 demo work is in scope.

## TDD slices

1. **Security and context primitives**
   - RED: recursive secret, prompt, notification-address, and untrusted-text redaction.
   - RED: validated correlation context and stable propagation headers.
   - GREEN: small infrastructure modules with no business dependencies.
2. **Bounded telemetry**
   - RED: service/provider/tool/graph/alert/queue/cost/evaluation metrics and forbidden labels.
   - GREEN: Prometheus-backed registry plus structured JSON logging and OTel spans.
3. **End-to-end correlation**
   - RED: HTTP admission -> worker -> graph event -> MCP/provider -> DB/SSE keeps one path.
   - GREEN: middleware, Celery headers, run events, audit metadata, and SSE payload propagation.
4. **Recovery behavior**
   - RED: expired worker lease recovery, Redis stream loss/restart, provider circuit opening,
     policy rollback authorization, and idempotent portfolio fill protection.
   - GREEN: deterministic recovery services with PostgreSQL as source of truth.
5. **Operations assets**
   - RED: contract tests require OTel, Prometheus, Grafana configuration and exact runbooks.
   - GREEN: compose services, bounded-label dashboard panels, security guide, and executable
     provider-outage/stuck-run/redis-loss/db-restore/policy-rollback runbooks with RPO/RTO.

## Verification and delivery

- Run each focused RED test before implementation and record the failing reason.
- Run focused GREEN and related integration tests after each slice.
- Run the locked Task 17 command and `make verify`.
- Review the full diff for correctness, security, recovery semantics, and unnecessary complexity.
- Fix all P0/P1/P2 findings, then commit, push, open PR, wait for CI, re-review remote diff, merge,
  and only then mark FRE-21 Done and append the final Notion merge record.

