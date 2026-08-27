# Ingestion recovery

Use this runbook when a provider ingestion job stops between durable commit boundaries. Never
substitute fixture data for a failed live provider response.

## Commit boundaries

1. **MinIO**: confirm the immutable response object exists and its content hash matches the
   outbox payload. An orphaned MinIO object is safe to retain; do not invent a database row.
2. **raw**: confirm `raw_data_object` contains the same provider, feed, object key, and hash.
   A retry must reuse the deterministic identity rather than duplicate the raw fact.
3. **outbox**: replay the pending outbox message only after the raw row is durable. Consumers
   must remain idempotent when the same message is delivered again.
4. **normalize**: retry normalization from the stored raw object. Never fetch a newer provider
   response during historical replay.
5. **fact**: persist facts only with their raw and normalized lineage; transaction rollback must
   leave no partial fact.
6. **quality**: persist the versioned quality observation in the same controlled retry flow.
   An error must leave no partial quality row.
7. **cursor**: advance the cursor last, using generation compare-and-swap. A stale worker must
   fail the CAS and must not move the watermark.

## Verification

Run `scripts/verify-ingestion.sh`. It exercises raw/MinIO replay, duplicate delivery, fact and
quality persistence, lease loss, cursor CAS, pagination recovery, credential redaction, and the
explicit live-provider gates. Missing live credentials are reported as `SKIP`, never converted
to fixture success.

To recover expired durable ingestion leases without touching raw or fact history, run
`uv run python scripts/recovery_probe.py ingestion-leases --database-url "$DATABASE_URL"`.
The command uses the production compare-and-swap job store and is idempotent; rerunning it reports
zero once no expired lease remains.

For full release evidence, run `make verify` after the focused gate and record both exit codes in
`docs/progress.md`.
