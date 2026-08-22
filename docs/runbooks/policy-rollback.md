# Policy rollback

## RPO

Zero loss: policy versions and promotion audit records are immutable history.

## RTO

Fifteen minutes after an authorized human selects the prior approved version.

```bash
curl -fsS http://localhost:8000/api/v1/policies
uv run pytest backend/tests/security/test_policy_promotion.py -q
docker compose exec postgres psql -U postgres -d stock_platform -c "select policy_kind,active_version from policy_control order by policy_kind;"
```

Use the authenticated promotion endpoint. Automatic or unauthenticated rollback must return 403.
