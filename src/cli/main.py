"""Entry point for the fishbot CLI."""

import typer

app = typer.Typer(name="fishbot", help="Personal fishing exploration bot.")


@app.command()
def run() -> None:
    """Start the fishing bot chat."""
    typer.echo("fishbot — not yet implemented. Sub-phase 1b will build this.")


@app.command()
def ingest() -> None:
    """Run data ingestion adapters."""
    typer.echo("ingest — not yet implemented. Sub-phase 1c and beyond will build this.")


if __name__ == "__main__":
    app()
