.PHONY: run test lint format ingest

run:
	uv run python -m src.cli.main run

test:
	uv run pytest tests/

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

ingest:
	uv run python -m src.cli.main ingest
