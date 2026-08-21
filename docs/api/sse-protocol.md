# Durable SSE protocol

`GET /api/v1/events?run_id=<uuid>` streams the authoritative `AgentEvent` sequence for one run.

- `id` is the durable event UUID and is sent back as `Last-Event-ID` when reconnecting.
- `event` is one of `run.started`, `node.started`, `tool.started`, `tool.completed`,
  `node.completed`, `checkpoint.saved`, `approval.requested`, `run.completed`, or `run.failed`.
- `data` is compact JSON containing `event_id`, `run_id`, `sequence`, `event_time`, `type`,
  `schema_version`, and a recursively redacted `payload`.
- Events are ordered by the per-run `sequence`. A cursor from another run returns
  `409 INVALID_LAST_EVENT_ID`.
- PostgreSQL is the replay and live-tail source. Redis can restart or be unavailable without losing
  events. The stream closes after all events for a terminal `COMPLETED`, `FAILED`, or `CANCELLED`
  run have been emitted.

Example:

```text
id: 0b98d99d-d280-4f20-b413-2d52a0cf7372
event: run.completed
data: {"event_id":"0b98d99d-d280-4f20-b413-2d52a0cf7372","run_id":"fe478853-d682-4a1d-904d-f7a962942b7b","sequence":9,"event_time":"2026-08-21T21:00:00+00:00","type":"run.completed","schema_version":"1.0","payload":{"status":"COMPLETED"}}
```
