# Security boundary

The platform is for research and **paper trading only**. It has no live broker endpoint,
credential, feature flag, or execution path. LLM output cannot place orders, notify users, change
risk rules, or activate policies. Policy promotion requires an authenticated human and an audit
record.

Operational telemetry must redact credentials, authorization headers, raw prompts containing
secrets, notification addresses, provider payloads, and untrusted full text. Logs may retain only
bounded identifiers, status codes, provider names, durations, and content hashes. Metrics must
never label by symbol, run ID, correlation ID, address, or raw content.

PostgreSQL is authoritative for AgentEvent, ToolCall, DecisionSnapshot, PaperFill, and CashLedger.
Redis streams and Celery delivery are transient and may be rebuilt without rewriting those facts.
Grafana requires authentication and all observability ports bind only to localhost by default.
OTLP export is disabled by default and, when explicitly enabled, is hard-coded to the loopback
Collector; configuration cannot redirect correlation identifiers to a remote endpoint.
