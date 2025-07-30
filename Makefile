# Bookmark Toolkit (BTK) Makefile
# Manage development, testing, and deployment tasks

.PHONY: help venv install install-dev test test-coverage lint format clean build docs serve-docs install-mcp test-mcp all check pre-commit

# Python interpreter to use
PYTHON := python3
VENV := .venv
VENV_BIN := $(VENV)/bin

# Check if we're in a virtual environment
IN_VENV := $(shell python -c 'import sys; print(int(hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)))')

# Default target - show help
help:
	@echo "Bookmark Toolkit (BTK) - Development Commands"
	@echo "============================================"
	@echo ""
	@echo "Environment Setup:"
	@echo "  make venv          - Create virtual environment"
	@echo "  make clean-venv    - Remove virtual environment"
	@echo ""
	@echo "Development Setup:"
	@echo "  make install        - Install BTK in production mode"
	@echo "  make install-dev    - Install BTK with development dependencies"
	@echo "  make install-mcp    - Install MCP server dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test          - Run all tests"
	@echo "  make test-coverage - Run tests with coverage report"
	@echo "  make test-mcp      - Test MCP server"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          - Run linting checks (flake8)"
	@echo "  make format        - Format code with black"
	@echo "  make typecheck     - Run type checking with mypy"
	@echo "  make check         - Run all quality checks (lint + format-check + typecheck)"
	@echo "  make pre-commit    - Run pre-commit hooks"
	@echo ""
	@echo "Building:"
	@echo "  make build         - Build distribution packages"
	@echo "  make clean         - Clean build artifacts"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs          - Generate documentation"
	@echo "  make serve-docs    - Serve documentation locally"
	@echo ""
	@echo "Shortcuts:"
	@echo "  make all           - Run clean, install-dev, check, and test-coverage"
	@echo ""
	@echo "Note: Most commands will create and use a virtual environment automatically."

# Create virtual environment
venv:
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating virtual environment..."; \
		$(PYTHON) -m venv $(VENV); \
		echo "Virtual environment created at $(VENV)"; \
		echo "Upgrading pip..."; \
		$(VENV_BIN)/pip install --upgrade pip setuptools wheel; \
	else \
		echo "Virtual environment already exists at $(VENV)"; \
	fi

# Remove virtual environment
clean-venv:
	@echo "Removing virtual environment..."
	rm -rf $(VENV)

# Install BTK in production mode
install: venv
	$(VENV_BIN)/pip install -e .

# Install BTK with development dependencies
install-dev: venv
	$(VENV_BIN)/pip install -e .
	$(VENV_BIN)/pip install -r requirements-dev.txt
	$(VENV_BIN)/pre-commit install

# Install MCP server dependencies
install-mcp:
	cd integrations/mcp-btk && npm install

# Run all tests
test: venv
	$(VENV_BIN)/pytest -v

# Run tests with coverage report
test-coverage: venv
	$(VENV_BIN)/pytest -v --cov=btk --cov-report=term-missing --cov-report=html

# Run linting
lint: venv
	$(VENV_BIN)/flake8 btk tests

# Format code with black
format: venv
	$(VENV_BIN)/black btk tests

# Check if code is formatted correctly (CI-friendly)
format-check: venv
	$(VENV_BIN)/black --check btk tests

# Run type checking
typecheck: venv
	$(VENV_BIN)/mypy btk

# Run all quality checks
check: lint format-check typecheck

# Run pre-commit hooks
pre-commit: venv
	$(VENV_BIN)/pre-commit run --all-files

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Clean everything including venv
clean-all: clean clean-venv

# Build distribution packages
build: clean venv
	$(VENV_BIN)/pip install build
	$(VENV_BIN)/python -m build

# Generate documentation (placeholder - implement when docs are set up)
docs:
	@echo "Documentation generation not yet configured"
	@echo "TODO: Set up Sphinx or similar documentation tool"

# Serve documentation locally
serve-docs: docs
	@echo "Documentation server not yet configured"

# Test MCP server
test-mcp:
	@echo "Testing MCP server..."
	@cd integrations/mcp-btk && npm test

# Run everything - full development cycle
all: clean install-dev check test-coverage

# Quick test target for development
quick-test: venv
	$(VENV_BIN)/pytest -v -x --tb=short

# Install and run all checks - useful for CI
ci: install-dev check test-coverage

# Update all dependencies
update-deps: venv
	$(VENV_BIN)/pip install --upgrade pip setuptools wheel
	$(VENV_BIN)/pip install --upgrade -r requirements-dev.txt
	cd integrations/mcp-btk && npm update

# Create a new bookmark library for testing
test-lib: venv install
	mkdir -p test-bookmarks
	$(VENV_BIN)/btk import nbf tests/fixtures/bookmarks.html --lib-dir test-bookmarks

# Run a specific test file
test-file: venv
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make test-file FILE=tests/test_utils.py"; \
		exit 1; \
	fi
	$(VENV_BIN)/pytest -v $(FILE)

# Run tests matching a pattern
test-match: venv
	@if [ -z "$(MATCH)" ]; then \
		echo "Usage: make test-match MATCH=test_import"; \
		exit 1; \
	fi
	$(VENV_BIN)/pytest -v -k $(MATCH)

# Show test coverage in browser
coverage-html: test-coverage
	open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html 2>/dev/null || echo "Please open htmlcov/index.html in your browser"

# Check for security vulnerabilities
security: venv
	$(VENV_BIN)/pip install safety
	$(VENV_BIN)/safety check

# Run BTK with a test library
run: venv install
	$(VENV_BIN)/btk --help

# Development shell with all dependencies
shell: venv install-dev
	@echo "Entering development shell with BTK environment..."
	@echo "Virtual environment activated at $(VENV)"
	@echo "Run 'deactivate' to exit the virtual environment"
	@bash --init-file <(echo "source $(VENV_BIN)/activate")

# Git pre-push hook - run before pushing
pre-push: check test

# Package for PyPI
package: clean build
	@echo "Packages built in dist/"
	@echo "To upload to PyPI: twine upload dist/*"

# Check if all dependencies are installed
check-deps:
	@echo "Checking Python dependencies..."
	@pip check
	@echo ""
	@echo "Checking Node.js dependencies for MCP..."
	@cd integrations/mcp-btk && npm list --depth=0

# Create necessary directories
setup-dirs:
	mkdir -p tests/fixtures
	mkdir -p docs
	mkdir -p scripts

# Initialize git hooks
init-hooks:
	pre-commit install
	pre-commit install --hook-type pre-push

# Full project setup from scratch
setup: setup-dirs install-dev install-mcp init-hooks
	@echo "Project setup complete!"
	@echo "Run 'make test' to verify everything is working."