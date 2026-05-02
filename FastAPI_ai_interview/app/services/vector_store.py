"""FAISS vector store for document embeddings and similarity search."""

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_embedding_model = None
_VECTOR_DIR = Path(settings.FAISS_DIR)


def _get_embedding_model():
    """Lazy-load the sentence-transformers embedding model."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # Use a multilingual model that supports Chinese
            model_name = "BAAI/bge-small-zh-v1.5"
            _embedding_model = SentenceTransformer(model_name)
            logger.info(f"Embedding model loaded: {model_name}")
        except ImportError:
            logger.error("sentence-transformers not installed")
            raise
    return _embedding_model


def _ensure_dir():
    _VECTOR_DIR.mkdir(parents=True, exist_ok=True)


def _get_index_path(document_id: int) -> Path:
    return _VECTOR_DIR / f"doc_{document_id}.faiss"


def _get_meta_path(document_id: int) -> Path:
    return _VECTOR_DIR / f"doc_{document_id}.meta.json"


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of text chunks."""
    model = _get_embedding_model()
    # Run in thread since sentence-transformers is sync
    import asyncio
    embeddings = await asyncio.to_thread(
        model.encode, texts, normalize_embeddings=True, show_progress_bar=False
    )
    return embeddings.tolist()


async def embed_query(query: str) -> list[float]:
    """Generate embedding for a single query string."""
    model = _get_embedding_model()
    import asyncio
    embedding = await asyncio.to_thread(
        model.encode, [query], normalize_embeddings=True, show_progress_bar=False
    )
    return embedding[0].tolist()


async def add_document(document_id: int, chunks: list[str]) -> int:
    """Add document chunks to the FAISS index. Returns the number of chunks indexed."""
    if not chunks:
        return 0

    import faiss
    embeddings = await embed_texts(chunks)
    dim = len(embeddings[0])
    embeddings_np = np.array(embeddings, dtype=np.float32)

    index = faiss.IndexFlatIP(dim)  # Inner Product (cosine similarity with normalized vectors)
    index.add(embeddings_np)

    _ensure_dir()
    faiss.write_index(index, str(_get_index_path(document_id)))

    # Store chunks metadata
    meta = {"document_id": document_id, "chunks": chunks, "dim": dim}
    _get_meta_path(document_id).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    logger.info(f"FAISS index created: doc_id={document_id}, chunks={len(chunks)}, dim={dim}")
    return len(chunks)


async def search_document(
    document_id: int, query: str, top_k: int = 5
) -> list[dict[str, Any]]:
    """Search for similar chunks in a specific document's index."""
    return await search_all(query, top_k=top_k, document_ids=[document_id])


async def search_all(
    query: str, top_k: int = 5, document_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    """Search across all (or specified) document indexes."""
    import faiss
    query_embedding = await embed_query(query)
    query_np = np.array([query_embedding], dtype=np.float32)

    all_results = []

    _ensure_dir()
    for idx_path in _VECTOR_DIR.glob("doc_*.faiss"):
        doc_id = int(idx_path.stem.split("_")[1])
        if document_ids and doc_id not in document_ids:
            continue

        meta_path = _get_meta_path(doc_id)
        if not meta_path.exists():
            continue

        try:
            index = faiss.read_index(str(idx_path))
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            chunks = meta["chunks"]

            scores, indices = index.search(query_np, min(top_k, len(chunks)))
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(chunks):
                    continue
                all_results.append({
                    "document_id": doc_id,
                    "chunk_index": int(idx),
                    "text": chunks[idx],
                    "score": float(score),
                })
        except Exception as e:
            logger.warning(f"FAISS search failed for doc {doc_id}: {e}")

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k]


async def delete_document(document_id: int) -> bool:
    """Delete a document's FAISS index and metadata."""
    idx_path = _get_index_path(document_id)
    meta_path = _get_meta_path(document_id)
    deleted = False

    if idx_path.exists():
        idx_path.unlink()
        deleted = True
        logger.info(f"FAISS index deleted: doc_id={document_id}")
    if meta_path.exists():
        meta_path.unlink()
        logger.info(f"FAISS metadata deleted: doc_id={document_id}")

    return deleted


async def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 100) -> list[str]:
    """Split text into chunks using LangChain's text splitter."""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "],
        )
        chunks = splitter.split_text(text)
        return [c.strip() for c in chunks if c.strip()]
    except ImportError:
        # Fallback: simple sentence-based splitting
        logger.warning("langchain_text_splitters not available, using simple split")
        chunks = []
        for sep in ["\n\n", "\n", "。"]:
            if chunks:
                break
            chunks = [c.strip() for c in text.split(sep) if c.strip()]
        if not chunks:
            chunks = [text]
        return chunks
