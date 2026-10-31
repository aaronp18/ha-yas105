.PHONY: help setup check test lint format fix version docker-build

help:
	@echo "setup         Install runtime + dev dependencies (uv sync --all-groups)"
	@echo "check         Lint, format check, and tests (run this before finishing)"
	@echo "test          Run the pytest suite"
	@echo "lint          Ruff lint + format check"
	@echo "format        Apply Ruff formatting"
	@echo "fix           Apply Ruff lint fixes and formatting"
	@echo "version       Print the installed CLI version"
	@echo "docker-build  Build the container image with Docker Compose"

setup:
	uv sync --all-groups

check: lint test

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

fix:
	uv run ruff check --fix .
	uv run ruff format .

version:
	uv run ha-yas105 version

docker-build:
	docker compose build
