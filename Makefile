.PHONY: bootstrap up down seed clean-fixtures verify smoke

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

smoke:
	./scripts/smoke.sh
