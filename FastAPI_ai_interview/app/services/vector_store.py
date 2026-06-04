"""FAISS vector store — unified index with smart chunking and embedding cache."""

import asyncio
import json
import logging
import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_embedding_model = None
_redis_pool = None
_VECTOR_DIR = Path(settings.FAISS_DIR)
_UNIFIED_INDEX = _VECTOR_DIR / "unified.faiss"
_UNIFIED_REGISTRY = _VECTOR_DIR / "unified.registry.json"

_write_lock = asyncio.Lock()


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from pathlib import Path as _Path
        import os as _os

        # Set HF cache to writable dir BEFORE any model load attempt
        _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        model_cache = (_VECTOR_DIR.parent / "models").resolve()
        model_cache.mkdir(parents=True, exist_ok=True)
        _os.environ["HF_HOME"] = str(model_cache)

        model_name = "BAAI/bge-small-zh-v1.5"
        cache_root = (_VECTOR_DIR.parent / "models").resolve()
        model_dir = cache_root / "bge-small-zh-v1.5"

        # Find model in cache (ModelScope or HuggingFace)
        if not model_dir.exists():
            for d in cache_root.glob("**/bge-small-zh*"):
                if d.is_dir():
                    model_dir = d
                    break

        if not model_dir.exists():
            try:
                from modelscope.hub.snapshot_download import snapshot_download
                snapshot_download("BAAI/bge-small-zh-v1.5", cache_dir=str(cache_root))
                for d in cache_root.glob("**/bge-small-zh*"):
                    if d.is_dir():
                        model_dir = d
                        break
                logger.info(f"ModelScope downloaded: {model_dir}")
            except Exception as e:
                logger.warning(f"ModelScope failed: {e}, falling back to HuggingFace")
                import os as _os
                _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

        from sentence_transformers import SentenceTransformer
        if model_dir.exists():
            try:
                _embedding_model = SentenceTransformer(str(model_dir.resolve()))
            except Exception as e:
                logger.warning(f"Local model load failed ({e}), downloading from hub...")
                import shutil
                shutil.rmtree(str(model_dir.resolve()), ignore_errors=True)
                _embedding_model = SentenceTransformer(model_name)
        else:
            _embedding_model = SentenceTransformer(model_name)
        logger.info(f"Embedding model loaded: {model_name}")
    return _embedding_model


def _ensure_dir():
    _VECTOR_DIR.mkdir(parents=True, exist_ok=True)


# ── Registry ──

def _load_registry() -> dict:
    if _UNIFIED_REGISTRY.exists():
        return json.loads(_UNIFIED_REGISTRY.read_text(encoding="utf-8"))
    return {"documents": {}, "next_vector_id": 0}


def _save_registry(reg: dict):
    _ensure_dir()
    _UNIFIED_REGISTRY.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")


# ── Embedding Cache ──

def _cache_key(query: str) -> str:
    return f"emb:{hashlib.md5(query.encode()).hexdigest()}"


async def _get_redis():
    global _redis_pool
    if _redis_pool is None:
        import redis.asyncio as redis
        _redis_pool = redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis_pool


async def _cached_embed_query(query: str) -> list[float]:
    key = _cache_key(query)
    try:
        r = await _get_redis()
        cached = await r.get(key)
        if cached:
            return list(np.frombuffer(cached, dtype=np.float32))
    except Exception:
        pass

    model = _get_embedding_model()
    embedding = await asyncio.to_thread(
        model.encode, [query], normalize_embeddings=True, show_progress_bar=False
    )
    result = embedding[0].tolist()

    try:
        r = await _get_redis()
        await r.setex(key, 3600, np.array(result, dtype=np.float32).tobytes())
    except Exception:
        pass

    return result


# ── Smart Chunking ──

async def chunk_text(text: str, filename: str = "", ext: str = ".txt",
                     chunk_size: int = 800, chunk_overlap: int = 150) -> list[str]:
    if not text.strip():
        return []

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if ext == ".pdf":
        pages = [p.strip() for p in text.split("\n") if len(p.strip()) > 50]
        chunks = []
        for page in pages:
            if len(page) <= chunk_size + chunk_overlap:
                chunks.append(f"[文档:{filename}] {page}")
            else:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                    separators=["\n\n", "\n", "。", ".", " ", ""]
                )
                for c in splitter.split_text(page):
                    chunks.append(f"[文档:{filename}] {c}")
        return chunks

    if ext == ".docx":
        paragraphs = text.split("\n")
        merged = []
        buf = ""
        for p in paragraphs:
            p = p.strip()
            if not p:
                if buf:
                    merged.append(buf)
                    buf = ""
                continue
            if len(buf) + len(p) < chunk_size * 0.7:
                buf = (buf + "\n" + p).strip()
            else:
                if buf:
                    merged.append(buf)
                buf = p
        if buf:
            merged.append(buf)

        chunks = []
        for block in merged:
            if len(block) <= chunk_size + chunk_overlap:
                chunks.append(f"[文档:{filename}] {block}")
            else:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                    separators=["\n\n", "\n", "。", ".", " ", ""]
                )
                for c in splitter.split_text(block):
                    chunks.append(f"[文档:{filename}] {c}")
        return chunks

    # TXT/MD/others
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "],
    )
    return [f"[文档:{filename}] {c.strip()}" for c in splitter.split_text(text) if c.strip()]


# ── Embeddings ──

async def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_embedding_model()
    embeddings = await asyncio.to_thread(
        model.encode, texts, normalize_embeddings=True, show_progress_bar=False
    )
    return embeddings.tolist()


async def embed_query(query: str) -> list[float]:
    return await _cached_embed_query(query)


# ── Unified Index Operations ──

def _open_index():
    import faiss
    _ensure_dir()
    if _UNIFIED_INDEX.exists():
        return faiss.read_index(str(_UNIFIED_INDEX))
    dim = _get_embedding_model().get_sentence_embedding_dimension()
    base = faiss.IndexFlatIP(dim)
    return faiss.IndexIDMap(base)


async def add_document(document_id: int, chunks: list[str]) -> int:
    if not chunks:
        return 0

    embeddings = await embed_texts(chunks)
    embeddings_np = np.array(embeddings, dtype=np.float32)
    import faiss

    async with _write_lock:
        index = _open_index()
        reg = _load_registry()

        start_id = reg["next_vector_id"]
        n = len(chunks)
        ids = np.arange(start_id, start_id + n, dtype=np.int64)

        index.add_with_ids(embeddings_np, ids)

        reg["documents"][str(document_id)] = {
            "vector_ids": list(range(start_id, start_id + n)),
            "chunks": chunks,
        }
        reg["next_vector_id"] = start_id + n

        faiss.write_index(index, str(_UNIFIED_INDEX))
        _save_registry(reg)

    logger.info(f"FAISS added: doc_id={document_id}, chunks={n}, ids={start_id}-{start_id + n - 1}")
    return n


async def search_all(
    query: str, top_k: int = 5, document_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    import faiss

    query_embedding = await _cached_embed_query(query)
    query_np = np.array([query_embedding], dtype=np.float32)

    if not _UNIFIED_INDEX.exists():
        return []

    index = faiss.read_index(str(_UNIFIED_INDEX))
    reg = _load_registry()
    docs = reg.get("documents", {})

    if not docs:
        return []

    limit = min(top_k * 3, index.ntotal) or top_k
    scores, ids = index.search(query_np, limit)

    # Build vid→(doc_id, idx) lookup in O(docs) since vector IDs are sequential per doc
    vid_map: dict[int, tuple[int, int]] = {}
    for doc_id_str, info in docs.items():
        vids = info["vector_ids"]
        if vids:
            base = vids[0]
            for i in range(len(vids)):
                vid_map[base + i] = (int(doc_id_str), i)

    results = []
    for score, vid in zip(scores[0], ids[0]):
        if vid < 0 or vid not in vid_map:
            continue
        doc_id, idx = vid_map[vid]
        chunks = docs[str(doc_id)]["chunks"]
        if 0 <= idx < len(chunks):
            results.append({
                "document_id": doc_id,
                "chunk_index": idx,
                "text": chunks[idx],
                "score": float(score),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


async def search_document(
    document_id: int, query: str, top_k: int = 5
) -> list[dict[str, Any]]:
    return await search_all(query, top_k=top_k, document_ids=[document_id])


async def delete_document(document_id: int) -> bool:
    import faiss

    async with _write_lock:
        if not _UNIFIED_INDEX.exists():
            return False

        reg = _load_registry()
        doc_key = str(document_id)
        if doc_key not in reg["documents"]:
            return False

        info = reg["documents"].pop(doc_key)
        ids_to_remove = np.array(info["vector_ids"], dtype=np.int64)

        index = faiss.read_index(str(_UNIFIED_INDEX))
        try:
            index.remove_ids(ids_to_remove)
        except Exception:
            # Fallback: rebuild without this doc
            dim = index.d if hasattr(index, 'd') else index.index.d
            new_base = faiss.IndexFlatIP(dim)
            new_index = faiss.IndexIDMap(new_base)
            next_id = 0
            for did_str, dinfo in reg["documents"].items():
                embs = [await embed_texts([c]) for c in dinfo["chunks"]]
                embs_flat = [e[0] for e in embs]
                if embs_flat:
                    arr = np.array(embs_flat, dtype=np.float32)
                    nids = np.arange(next_id, next_id + len(embs_flat), dtype=np.int64)
                    new_index.add_with_ids(arr, nids)
                    dinfo["vector_ids"] = list(range(next_id, next_id + len(embs_flat)))
                    next_id += len(embs_flat)
            reg["next_vector_id"] = next_id
            index = new_index

        faiss.write_index(index, str(_UNIFIED_INDEX))
        _save_registry(reg)

    logger.info(f"FAISS deleted: doc_id={document_id}, vectors_removed={len(info['vector_ids'])}")
    return True


async def rebuild_index():
    _ensure_dir()
    if _UNIFIED_INDEX.exists():
        logger.info("Unified index exists, skipping migration")
        return

    old_files = sorted(_VECTOR_DIR.glob("doc_*.faiss"))
    if not old_files:
        logger.info("No old index files to migrate")
        return

    import faiss
    logger.info(f"Migrating {len(old_files)} old indexes to unified index...")

    reg = {"documents": {}, "next_vector_id": 0}
    dim = _get_embedding_model().get_sentence_embedding_dimension()
    new_index = faiss.IndexIDMap(faiss.IndexFlatIP(dim))

    for idx_path in old_files:
        doc_id = int(idx_path.stem.split("_")[1])
        meta_path = _VECTOR_DIR / f"doc_{doc_id}.meta.json"
        try:
            old_index = faiss.read_index(str(idx_path))
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            chunks = meta["chunks"]

            vectors = faiss.vector_to_array(old_index.xb) if hasattr(old_index, 'xb') else None
            if vectors is None:
                continue

            n = len(chunks)
            ids = np.arange(reg["next_vector_id"], reg["next_vector_id"] + n, dtype=np.int64)
            new_index.add_with_ids(vectors.reshape(n, -1).astype(np.float32), ids)
            reg["documents"][str(doc_id)] = {
                "vector_ids": list(range(reg["next_vector_id"], reg["next_vector_id"] + n)),
                "chunks": chunks,
            }
            reg["next_vector_id"] += n
            logger.info(f"  migrated doc {doc_id}: {n} chunks")
        except Exception as e:
            logger.warning(f"  skip doc {doc_id}: {e}")

    faiss.write_index(new_index, str(_UNIFIED_INDEX))
    _save_registry(reg)

    backup_dir = _VECTOR_DIR / "backup"
    backup_dir.mkdir(exist_ok=True)
    for idx_path in old_files:
        try:
            idx_path.rename(backup_dir / idx_path.name)
        except Exception:
            pass
        meta_path = _VECTOR_DIR / f"doc_{idx_path.stem.split('_')[1]}.meta.json"
        if meta_path.exists():
            try:
                meta_path.rename(backup_dir / meta_path.name)
            except Exception:
                pass

    logger.info(f"Migration complete: {len(old_files)} docs → unified.faiss")
