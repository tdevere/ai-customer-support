.PHONY: help install format lint test ci clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies (requires uv)
	python -m pip install --upgrade pip uv
	uv pip install --system -r requirements.txt

format: ## Auto-format code with black
	black .

lint: ## Run linting exactly as CI does (black + flake8)
	black --check .
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

test: ## Run tests with coverage (loads .env.test)
	@set -a && . ./.env.test && set +a && \
	pytest tests/ --cov=. --cov-report=xml --cov-report=term

ci: lint test ## Run full CI pipeline locally (lint + test)

clean: ## Remove generated artefacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -f coverage.xml .coverage
	rm -rf htmlcov/ .pytest_cache/
