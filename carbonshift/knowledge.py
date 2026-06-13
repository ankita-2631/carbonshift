"""Foundry IQ retrieval — grounds agent reasoning in the CarbonShift knowledge base.

Thin wrapper over the Azure AI Search index populated by scripts/upload_knowledge.py.
Returns relevant knowledge snippets (with their source) so agents can cite real data
instead of inventing numbers. Degrades gracefully to an empty result when Search is
not configured or unreachable, so the demo always runs.
"""
from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=128)
def retrieve(query: str, top: int = 3) -> tuple[tuple[str, str], ...]:
    """Return up to `top` (content, source) snippets relevant to `query`.

    Cached so repeated lookups for the same query do not re-hit the service.
    Returns an empty tuple if SEARCH_ENDPOINT is unset or the lookup fails.
    """
    endpoint = os.environ.get("SEARCH_ENDPOINT")
    index_name = os.environ.get("FOUNDRY_IQ_INDEX", "carbon-knowledge")
    if not endpoint:
        return ()

    try:
        from azure.identity import DefaultAzureCredential
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=DefaultAzureCredential(),
        )
        results = client.search(search_text=query, top=top)
        return tuple(
            (r.get("content", ""), r.get("source", "knowledge base"))
            for r in results
        )
    except Exception:
        return ()


def as_context(snippets: tuple[tuple[str, str], ...]) -> str:
    """Format retrieved snippets as a citable context block for an LLM prompt."""
    if not snippets:
        return "No knowledge-base context available."
    return "\n\n".join(
        f"[Source: {source}]\n{content}" for content, source in snippets
    )
