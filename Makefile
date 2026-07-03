# git-reaper dev rituals. Everything runs through uv.

UV ?= uv
VENV ?= .venv

.DEFAULT_GOAL := help

.PHONY: help setup activate fmt lint typecheck test cov check build clean run pulse docs docs-build

help: ## List the available rituals
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[35m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create the venv and install all deps (incl. dev group)
	$(UV) sync

fmt: ## Auto-format and fix lint findings
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

lint: ## Lint and check formatting (no changes)
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

typecheck: ## mypy over the typed core
	$(UV) run mypy

test: ## Run the test suite
	$(UV) run pytest

cov: ## Tests with coverage report
	$(UV) run pytest --cov=git_reaper --cov-report=term-missing

check: lint typecheck test ## The full gauntlet: lint + types + tests

docs: ## Serve the docs locally with live reload
	$(UV) run --group docs mkdocs serve

docs-build: ## Build the docs strictly (what CI runs)
	$(UV) run --group docs mkdocs build --strict

build: ## Build sdist and wheel into dist/
	$(UV) build

clean: ## Sweep build artifacts and caches
	rm -rf dist build site .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +

run: ## Run the CLI (ARGS="tree ." to pass arguments)
	$(UV) run reaper $(ARGS)

pulse: ## Signs-of-life check via the CLI
	$(UV) run reaper pulse

summon: ## Summon the reaper (for testing the TUI)
	$(UV) run reaper summon
