"""Interactive chat loop using the Anthropic SDK + rich for terminal I/O."""

from anthropic import Anthropic, APIError
from rich.console import Console

from src.agent.client import get_client, get_model
from src.agent.system_prompt import assemble, load_template
from src.jurisdictions.registry import get_jurisdiction
from src.storage.database import get_db
from src.storage.profile import load_profile
from src.storage.trips import recent_trips

EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}


def run_chat() -> None:
    console = Console()

    try:
        client = get_client()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        return

    profile = load_profile()
    db = get_db()
    trips = recent_trips(db, limit=5)
    home = get_jurisdiction(profile.home_jurisdiction)
    system_prompt = assemble(load_template(), profile, trips, home)
    model = get_model()

    console.print(f"[dim]fishbot — {model} — type /exit to quit[/dim]")
    console.print()

    messages: list[dict] = []

    while True:
        try:
            user_input = console.input("[bold cyan]> [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            console.print("[dim]bye[/dim]")
            return

        if not user_input:
            continue

        if user_input.lower() in EXIT_COMMANDS:
            console.print("[dim]bye[/dim]")
            return

        messages.append({"role": "user", "content": user_input})

        try:
            response_text = _stream_response(
                client, model, system_prompt, messages, console
            )
        except APIError as e:
            console.print(f"[red]API error: {e}[/red]")
            messages.pop()
            continue
        except KeyboardInterrupt:
            console.print()
            console.print("[dim](interrupted)[/dim]")
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": response_text})


def _stream_response(
    client: Anthropic,
    model: str,
    system_prompt: str,
    messages: list[dict],
    console: Console,
) -> str:
    chunks: list[str] = []
    with client.messages.stream(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
            console.print(text, end="", markup=False, highlight=False, soft_wrap=True)
    console.print()
    console.print()
    return "".join(chunks)
