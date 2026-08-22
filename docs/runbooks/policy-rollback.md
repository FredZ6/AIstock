# Policy rollback

## RPO

Zero loss: policy versions and promotion audit records are immutable history.

## RTO

Fifteen minutes after an authorized human selects the prior approved version.

```bash
docker compose exec postgres psql -U postgres -d stock_platform -c "select policy_kind,active_version from policy_control order by policy_kind;"
export POLICY_ID='<approved-candidate-uuid>'
export EXPECTED_REVISION='<current-policy-control-revision>'
export ADMIN_API_TOKEN='<deployment-secret>'
curl -fsS -X POST "http://localhost:8000/api/v1/policies/${POLICY_ID}/rollback" -H "Authorization: Bearer ${ADMIN_API_TOKEN}" -H 'Content-Type: application/json' --data "{\"rationale\":\"incident rollback\",\"expected_revision\":${EXPECTED_REVISION}}"
uv run pytest backend/tests/security/test_policy_promotion.py backend/tests/integration/learning/test_weekly_review.py -q
```

The API process must already have matching `ADMIN_API_TOKEN` and fixed `ADMIN_ACTOR_ID` environment
settings. The actor identity comes from server configuration, never the request body. Automatic or
unauthenticated rollback must return 403; verify the active version and audit row after the POST.
