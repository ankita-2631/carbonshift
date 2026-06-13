"""Upload the CarbonShift knowledge base into Azure AI Search for Foundry IQ grounding.

Splits the markdown docs in ./knowledge into chunks and pushes them to a search index.
Run once after provisioning:

    python scripts/upload_knowledge.py

Required env vars (see .env.example):
    SEARCH_ENDPOINT   e.g. https://carbonshift-search-8865.search.windows.net
    FOUNDRY_IQ_INDEX  e.g. carbon-knowledge

Auth uses DefaultAzureCredential (az login). The signed-in identity needs
"Search Index Data Contributor" and "Search Service Contributor" on the search service.
"""
from __future__ import annotations

import os
import pathlib
import sys

KNOWLEDGE_DIR = pathlib.Path(__file__).resolve().parent.parent / "knowledge"

# Load .env from the project root so SEARCH_ENDPOINT etc. are available.
try:
    from dotenv import load_dotenv

    load_dotenv(KNOWLEDGE_DIR.parent / ".env")
except Exception:
    pass


def chunk_markdown(text: str, max_chars: int = 1200) -> list[str]:
    """Split on blank-line paragraphs, packing into <= max_chars chunks."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 > max_chars and buf:
            chunks.append(buf.strip())
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def main() -> int:
    endpoint = os.environ.get("SEARCH_ENDPOINT")
    index_name = os.environ.get("FOUNDRY_IQ_INDEX", "carbon-knowledge")
    if not endpoint:
        print("SEARCH_ENDPOINT is not set. See .env.example.", file=sys.stderr)
        return 1

    from azure.core.credentials import AzureKeyCredential  # noqa: F401  (key auth optional)
    from azure.identity import DefaultAzureCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        SearchableField,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SimpleField,
    )

    credential = DefaultAzureCredential()

    # 1) Create the index if it does not exist.
    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
    ]
    existing = {idx.name for idx in index_client.list_indexes()}
    if index_name not in existing:
        index_client.create_index(SearchIndex(name=index_name, fields=fields))
        print(f"Created index '{index_name}'.")
    else:
        print(f"Index '{index_name}' already exists.")

    # 2) Build documents from the knowledge markdown.
    docs = []
    for md in sorted(KNOWLEDGE_DIR.glob("*.md")):
        for i, chunk in enumerate(chunk_markdown(md.read_text(encoding="utf-8"))):
            docs.append(
                {
                    "id": f"{md.stem}-{i}",
                    "content": chunk,
                    "source": md.name,
                }
            )

    # 3) Upload.
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)
    result = search_client.upload_documents(documents=docs)
    succeeded = sum(1 for r in result if r.succeeded)
    print(f"Uploaded {succeeded}/{len(docs)} chunks to '{index_name}'.")
    return 0 if succeeded == len(docs) else 2


if __name__ == "__main__":
    raise SystemExit(main())
