.PHONY: bootstrap up down seed clean-fixtures verify evaluate smoke alpaca-stream

bootstrap:
	./scripts/bootstrap.sh

up:
	docker compose up -d

down:
	docker compose down

seed:
	PYTHONPATH="$(CURDIR)/backend/src" UV_CACHE_DIR="$(CURDIR)/.uv-cache" uv run python scripts/seed_demo.py

clean-fixtures:
	docker compose down --volumes --remove-orphans

verify:
	./scripts/verify.sh

evaluate:
	PYTHONPATH="$(CURDIR)/backend/src" UV_CACHE_DIR="$(CURDIR)/.uv-cache" uv run python scripts/run_offline_eval.py --dataset evals/datasets --baseline evals/baselines/eval-v0.2.0.json --output reports/evaluation/latest

smoke:
	./scripts/smoke.sh

alpaca-stream:
	PYTHONPATH="$(CURDIR)/backend/src" UV_CACHE_DIR="$(CURDIR)/.uv-cache" uv run python scripts/run_alpaca_stream.py
