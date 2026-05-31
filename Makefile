.PHONY: run test lint format ingest ingest-hydat recent build-features train-sdm compute-access compute-untapped export-map

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

ingest-hydat:
	uv run python -m src.cli.main ingest-hydat

recent:
	uv run python -m src.cli.main recent

build-features:
	uv run python -m src.cli.main build-features

train-sdm:
	uv run python -m src.cli.main train-sdm

compute-access:
	uv run python -m src.cli.main compute-access

compute-untapped:
	uv run python -m src.cli.main compute-untapped

export-map:
	uv run python -m src.cli.export_map
	@echo "Open data/processed/map_index.html in your browser."
