.PHONY: help venv install-dev test test-coverage lint format typecheck check clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

help:
	@echo "bookmark-memex Development Commands"
	@echo "===================================="
	@echo "  make venv          - Create virtual environment"
	@echo "  make install-dev   - Install with dev dependencies"
	@echo "  make test          - Run all tests"
	@echo "  make test-coverage - Run tests with coverage"
	@echo "  make lint          - Run flake8"
	@echo "  make format        - Format with black"
	@echo "  make typecheck     - Run mypy"
	@echo "  make check         - All quality checks"
	@echo "  make clean         - Clean build artifacts"

venv:
	python3 -m venv $(VENV)

install-dev: venv
	$(PIP) install -e ".[dev,mcp]"

test: install-dev
	$(PYTEST) -v

test-coverage: install-dev
	$(PYTEST) --cov=bookmark_memex --cov-report=term-missing

lint: install-dev
	$(VENV)/bin/flake8 bookmark_memex tests --max-line-length 120

format: install-dev
	$(VENV)/bin/black bookmark_memex tests

typecheck: install-dev
	$(VENV)/bin/mypy bookmark_memex

check: lint typecheck

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
