.PHONY: help install install-dev test lint format clean start stop restart logs \
        generate-arup generate-singapore generate-baseline train evaluate \
        api ui mlflow shell ps infra

PYTHON := python3
PIP := $(PYTHON) -m pip
COMPOSE := docker compose

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────────────────────

install:  ## Install production dependencies
	$(PIP) install -r requirements.txt

install-dev:  ## Install dev dependencies
	$(PIP) install -r requirements.txt -r requirements-dev.txt

test:  ## Run test suite
	$(PYTHON) -m pytest tests/ -v --tb=short

lint:  ## Run linters
	$(PYTHON) -m ruff check src/ lambdas/ app/ tests/
	$(PYTHON) -m mypy src/ --ignore-missing-imports

format:  ## Auto-format code
	$(PYTHON) -m black src/ lambdas/ app/ tests/
	$(PYTHON) -m ruff check --fix src/ lambdas/ app/ tests/

clean:  ## Clean build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache/ .coverage htmlcov/ build/ dist/ *.egg-info/

# ── Local infrastructure ────────────────────────────────────────────────

start:  ## Start local Docker stack (Redpanda, Neo4j, Postgres, MinIO, MLflow)
	$(COMPOSE) up -d
	@echo "Waiting for services to be ready..."
	@sleep 15
	@$(COMPOSE) ps

stop:  ## Stop local Docker stack
	$(COMPOSE) down

restart: stop start  ## Restart local Docker stack

logs:  ## Tail logs from all services
	$(COMPOSE) logs -f

ps:  ## Show running services
	$(COMPOSE) ps

infra: start  ## Alias for start (local infrastructure)

# ── Event generation ─────────────────────────────────────────────────────

generate-arup:  ## Generate Arup attack pattern (15 wires, $25.6M)
	$(PYTHON) scripts/generate_events.py --pattern arup --target local --rate 100

generate-singapore:  ## Generate Singapore attack pattern (1 wire, $499K)
	$(PYTHON) scripts/generate_events.py --pattern singapore --target local --rate 50

generate-baseline:  ## Generate baseline traffic (10K users, 500/sec)
	$(PYTHON) scripts/generate_events.py --pattern baseline --target local --rate 500 --duration 60

generate-all:  ## Generate all three patterns in sequence
	$(PYTHON) scripts/generate_events.py --pattern mix --target local --rate 300

# ── ML pipeline ──────────────────────────────────────────────────────────

train:  ## Train XGBoost model on synthetic labels
	$(PYTHON) -m src.ml.train --config configs/xgb_v1.yaml

evaluate:  ## Evaluate trained model on holdout
	$(PYTHON) -m src.ml.evaluate --config configs/xgb_v1.yaml

# ── Services ─────────────────────────────────────────────────────────────

api:  ## Run FastAPI service (port 8000)
	$(PYTHON) -m uvicorn src.application.api:app --host 0.0.0.0 --port 8000 --reload

ui:  ## Run Streamlit UI (port 8501)
	$(PYTHON) -m streamlit run app/streamlit_app.py --server.port 8501

mlflow:  ## Run MLflow tracking server (port 5000)
	$(PYTHON) -m mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlruns

worker-feature:  ## Run feature computer worker (local)
	$(PYTHON) -m src.infrastructure.adapters.local.feature_computer

worker-graph:  ## Run graph updater worker (local)
	$(PYTHON) -m src.infrastructure.adapters.local.graph_updater

worker-score:  ## Run real-time scorer worker (local)
	$(PYTHON) -m src.infrastructure.adapters.local.scorer

shell:  ## Open Python shell with project context
	$(PYTHON) -c "import sys; sys.path.insert(0, '.'); import code; code.interact()"

# ── Deployment ──────────────────────────────────────────────────────────

deploy-aws:  ## Build Lambda zips and apply AWS Terraform
	bash scripts/deploy_aws.sh

deploy-gcp:  ## Apply GCP Terraform (portability reference)
	cd terraform/gcp && terraform init && terraform apply -auto-approve

build-lambdas:  ## Build Lambda deployment zips
	bash scripts/build_lambdas.sh

# ── Database ────────────────────────────────────────────────────────────

init-db:  ## Initialize the Postgres schema
	$(PYTHON) -c "from src.infrastructure.persistence import init_db; init_db()"

init-neo4j:  ## Initialize Neo4j constraints
	$(PYTHON) -c "from src.infrastructure.graph import get_graph_client; get_graph_client().init_schema()"

# ── All-in-one demo ─────────────────────────────────────────────────────

demo:  ## Run a full end-to-end demo (start stack, generate, train, evaluate)
	$(MAKE) start
	$(MAKE) init-db
	$(MAKE) init-neo4j
	$(MAKE) generate-all
	$(MAKE) train
	$(MAKE) evaluate

walkthrough:  ## Run a self-contained end-to-end walkthrough (no Docker required)
	$(PYTHON) -m examples.walkthrough

benchmark:  ## Measure scorer latency (p50/p95/p99)
	$(PYTHON) -m scripts.benchmark --n 5000

bench: benchmark  ## Alias for benchmark

# ── CI / Quality gates ──────────────────────────────────────────────────

ci:  ## Run the same checks as GitHub Actions
	@echo "== Lint =="
	$(PYTHON) -m ruff check src/ lambdas/ app/ tests/ scripts/ examples/
	@echo "== Format check =="
	$(PYTHON) -m black --check src/ lambdas/ app/ tests/ scripts/ examples/
	@echo "== Type check =="
	$(PYTHON) -m mypy src/ --ignore-missing-imports
	@echo "== Tests =="
	$(PYTHON) -m pytest tests/ -v --tb=short --cov=src --cov-report=term-missing
	@echo "== Walkthrough (smoke) =="
	$(PYTHON) -m examples.walkthrough | tail -5
	@echo "== Benchmark (smoke) =="
	$(PYTHON) -m scripts.benchmark --n 500 | tail -8

seed:  ## Seed the database with demo data
	$(PYTHON) -m scripts.seed_demo_data --baseline 2000 --arup --singapore

seed-small:  ## Seed with a smaller dataset (faster)
	$(PYTHON) -m scripts.seed_demo_data --baseline 200 --arup --singapore

# ── Investigator CLI shortcuts ──────────────────────────────────────────

cases:  ## List the 20 most recent cases
	$(PYTHON) -m examples.investigator_cli list --limit 20 --human

case:  ## Show a case by ID (usage: make case ID=<uuid>)
	$(PYTHON) -m examples.investigator_cli show $(ID) --human

cases-export:  ## Export all open cases to cases.csv
	$(PYTHON) -m examples.investigator_cli export --output cases.csv --status OPEN

# ── Training analysis ──────────────────────────────────────────────────

analyze:  ## Run the training analysis script
	$(PYTHON) -m notebooks.training_analysis
