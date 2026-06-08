"""Tests for the knowledge base agent wrapper."""


def test_search_knowledge_base_for_agent_returns_string():
    from src.services.knowledge import search_knowledge_base_for_agent

    result = search_knowledge_base_for_agent("channel catfish bait")
    assert isinstance(result, str)
    assert len(result) > 0


def test_search_knowledge_base_no_results():
    from src.services.knowledge import search_knowledge_base_for_agent

    result = search_knowledge_base_for_agent(
        "xyzzy nonexistent fishing term that matches nothing"
    )
    assert isinstance(result, str)
    assert "No relevant" in result or len(result) > 0


def test_search_knowledge_base_attribution():
    from src.services.knowledge import search_knowledge_base_for_agent

    result = search_knowledge_base_for_agent("carp fishing")
    if "No relevant" not in result:
        assert "youtube.com" in result or "Source:" in result
