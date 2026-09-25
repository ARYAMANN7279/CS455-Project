.PHONY: help dev up down logs test lint typecheck build sandbox chaos load docs

help:
	@echo "Targets:"
	@echo "  dev        Bring up the full local stack"
	@echo "  down       Stop and remove containers"
	@echo "  logs       Tail logs from all services"
	@echo "  test       Run backend unit + integration tests"
	@echo "  lint       Run ruff, mypy, bandit"
	@echo "  sandbox    Build the sandbox image"
	@echo "  chaos      Run the worker-kill chaos test (requires CONCORD_TOKEN env)"
	@echo "  load       Run the CRDT load test"
	@echo "  build      Build frontend production assets"

dev:
	docker compose up -d
	@echo "Frontend: http://localhost:5173"
	@echo "Backend:  http://localhost:8000/docs"

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose exec backend pytest

lint:
	docker compose exec backend ruff check .
	docker compose exec backend mypy app
	docker compose exec backend bandit -r app -ll

sandbox:
	docker build -t concord-sandbox:latest -f ./sandbox/Dockerfile ./sandbox
	docker build -t concord-sandbox-cpp:latest -f ./sandbox/Dockerfile.cpp ./sandbox
	docker build -t concord-sandbox-nodejs:latest -f ./sandbox/Dockerfile.nodejs ./sandbox

chaos:
	docker compose exec backend python scripts/chaos.py --token $(CONCORD_TOKEN) --session-id $(SESSION_ID) --file-id $(FILE_ID)

load:
	docker compose exec backend python scripts/load_test.py --clients 1 5 10 25

build:
	docker compose exec frontend npm run build
