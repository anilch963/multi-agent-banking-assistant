"""ChromaDB knowledge base: ingest the markdown product docs and search them.

    python -m app.rag.store            # ingest if the collection is empty
    python -m app.rag.store --force    # rebuild
"""
from __future__ import annotations

import os
import re
import sys
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from app import config


def _embedding_function():
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.environ["OPENAI_API_KEY"], model_name=config.OPENAI_EMBEDDING_MODEL
    )


@lru_cache(maxsize=1)
def get_collection():
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return client.get_or_create_collection(
        config.KB_COLLECTION, embedding_function=_embedding_function(), metadata={"hnsw:space": "cosine"}
    )


def chunk_markdown(path: Path) -> list[dict]:
    """One chunk per `##` section, prefixed with the document title for context."""
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^# (.+)$", text, flags=re.M)
    title = title_match.group(1).strip() if title_match else path.stem
    chunks = []
    for i, block in enumerate(re.split(r"^## ", text, flags=re.M)[1:]):
        heading, _, body = block.partition("\n")
        body = body.strip()
        if body:
            chunks.append({
                "id": f"{path.stem}-{i}",
                "text": f"{title} - {heading.strip()}\n{body}",
                "metadata": {"product": path.stem, "section": heading.strip(), "source": path.name},
            })
    return chunks


def ingest(force: bool = False, collection=None) -> int:
    """Load every knowledge_base/*.md file. Returns the number of chunks stored."""
    collection = collection or get_collection()
    if collection.count() and not force:
        return collection.count()
    chunks = [c for path in sorted(config.KB_DIR.glob("*.md")) for c in chunk_markdown(path)]
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    return len(chunks)


def search(query: str, product: str | None = None, k: int = 4, collection=None) -> list[dict]:
    collection = collection or get_collection()
    result = collection.query(
        query_texts=[query], n_results=k, where={"product": product} if product else None
    )
    return [
        {"text": doc, "source": meta["source"], "section": meta["section"], "distance": round(dist, 3)}
        for doc, meta, dist in zip(result["documents"][0], result["metadatas"][0], result["distances"][0])
    ]


if __name__ == "__main__":
    print(f"{ingest(force='--force' in sys.argv)} chunks in '{config.KB_COLLECTION}'")
