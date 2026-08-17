# M1 MCP Inspector evidence

Date: 2026-08-18  
Inspector: `@modelcontextprotocol/inspector@2.2.0`  
Transport: Streamable HTTP at `http://127.0.0.1:8000/mcp`

Each server was started locally in fixture mode and terminated automatically after the Inspector
command. No provider credentials or network market data were used.

## Tool discovery

- SEC: `tools/list` — exit 0 — `get_company_facts`, `get_filings`,
  `get_filing_sections`.
- Market: `tools/list` — exit 0 — `get_price_bars`, `get_company_news`,
  `get_option_aggregates`.
- Analyst: `tools/list` — exit 0 — `get_estimates`, `get_target_consensus`.

Every discovered tool reported:

- required inputs `symbol` and `as_of`;
- `additionalProperties: false`;
- a strict structured output schema whose envelope and every concrete record object reject
  additional properties;
- `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, and
  `openWorldHint: true`.

No order, notification, policy mutation, arbitrary URL, SQL, or shell tool was discoverable.

## Structured call

Command shape:

```text
npx -y @modelcontextprotocol/inspector@2.2.0 --cli \
  http://127.0.0.1:8000/mcp --transport http \
  --method tools/call --tool-name get_price_bars \
  --tool-args-json '{"symbol":"NVDA","as_of":"2026-08-16T00:00:00Z"}' \
  --format json
```

Result: exit 0 and `isError: false`. `structuredContent` contained `status: ok`, provider
`FIXTURE`, feed `price_bars`, `query_as_of`, `data_as_of`, `available_at`, freshness,
quality/missingness, three point-in-time records, citations, raw object keys, SHA-256 content
hashes, pagination, warnings, and a 32-character trace ID. The newest returned record had
`available_at=2026-08-15T20:01:00Z`, which is before the requested cutoff.

## Denial audit

Inspector called `get_price_bars` with an extra `sql` argument. The call was rejected with
`isError: true` and the Inspector exited 5. PostgreSQL recorded an append-only
`mcp.tool.denied` event with the tool name and a 64-character SHA-256 request fingerprint. The
event payload contained none of the raw `symbol`, `as_of`, or `sql` arguments.
