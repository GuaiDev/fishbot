"""Agent-facing wrapper for the RAG knowledge base search."""

from src.ingest.community.youtube_ingest import search_knowledge
from src.storage.database import get_db


def search_knowledge_base_for_agent(query: str, top_k: int = 5) -> str:
    db = get_db()
    results = search_knowledge(query, db, top_k=top_k)

    if not results:
        return "No relevant knowledge base results found for that query."

    lines = [f"Knowledge base results for '{query}':\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r['source_type'].upper()}] {r['title']}")
        lines.append(f"   Source: {r['url']}")
        lines.append(f"   Excerpt: ...{r['chunk_text'][:300]}...")
        lines.append("")

    return "\n".join(lines)
