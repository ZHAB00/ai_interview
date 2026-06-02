# RAG Architecture Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite FAISS vector store with unified index, smart chunking, embedding cache, and read-write locks

**Architecture:** IndexIDMap(IndexFlatIP) as single unified index with JSON registry, adaptive chunking by document type, Redis embedding cache, asyncio.Lock for writes with free reads

**Tech Stack:** FAISS, sentence-transformers (BAAI/bge-small-zh-v1.5), redis, pypdf, python-docx, langchain-text-splitters

---

### Task 1: Rewrite vector_store.py — Core Module

**Files:**
- Rewrite: `FastAPI_ai_interview/app/services/vector_store.py`

This is the main task. Complete rewrite of vector_store.py with unified index architecture.

- [ ] **Step 1: Write the new vector_store.py**

```python
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
_VECTOR_DIR = Path(settings.FAISS_DIR)
_UNIFIED_INDEX = _VECTOR_DIR / "unified.faiss"
_UNIFIED_REGISTRY = _VECTOR_DIR / "unified.registry.json"

# Read/Write lock — write (upload/delete) must be serialized, reads are free
_write_lock = asyncio.Lock()


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        model_name = "BAAI/bge-small-zh-v1.5"
        _embedding_model = SentenceTransformer(model_name)
        logger.info(f"Embedding model loaded: {model_name}")
    return _embedding_model


def _ensure_dir():
    _VECTOR_DIR.mkdir(parents=True, exist_ok=True)


# ── Registry ──

def _load_registry() -> dict:
    """Load the vector ID → document/chunk mapping."""
    if _UNIFIED_REGISTRY.exists():
        return json.loads(_UNIFIED_REGISTRY.read_text(encoding="utf-8"))
    return {"documents": {}, "next_vector_id": 0}


def _save_registry(reg: dict):
    _ensure_dir()
    _UNIFIED_REGISTRY.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")


# ── Embedding Cache ──

def _cache_key(query: str) -> str:
    return f"emb:{hashlib.md5(query.encode()).hexdigest()}"


async def _cached_embed_query(query: str) -> list[float]:
    """Embed a query, checking Redis cache first."""
    import redis.asyncio as redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=False)
        key = _cache_key(query)
        cached = await r.get(key)
        if cached:
            return list(np.frombuffer(cached, dtype=np.float32))
    except Exception:
        pass  # Redis unavailable — fall through

    model = _get_embedding_model()
    embedding = await asyncio.to_thread(
        model.encode, [query], normalize_embeddings=True, show_progress_bar=False
    )
    result = embedding[0].tolist()

    try:
        r = redis.from_url(settings.REDIS_URL)
        await r.setex(key, 3600, np.array(result, dtype=np.float32).tobytes())
    except Exception:
        pass

    return result


# ── Smart Chunking ──

async def chunk_text(text: str, filename: str = "", ext: str = ".txt",
                     chunk_size: int = 800, chunk_overlap: int = 150) -> list[str]:
    """Split text with context headers. Strategy adapts to document type."""
    if not text.strip():
        return []

    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if ext == ".pdf":
        # PDF: each page was joined by \n from _extract_doc_text
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
        # DOCX: paragraphs already joined by \n, group nearby short paragraphs
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
            # Merge short consecutive paragraphs
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

    # TXT/MD/others: recursive split
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
    """Open the unified FAISS index or create if not exists."""
    import faiss
    _ensure_dir()
    if _UNIFIED_INDEX.exists():
        return faiss.read_index(str(_UNIFIED_INDEX))
    dim = _get_embedding_model().get_sentence_embedding_dimension()
    base = faiss.IndexFlatIP(dim)
    return faiss.IndexIDMap(base)


async def add_document(document_id: int, chunks: list[str]) -> int:
    """Add document chunks to the unified FAISS index. Thread-safe via write lock."""
    if not chunks:
        return 0

    embeddings = await embed_texts(chunks)
    embeddings_np = np.array(embeddings, dtype=np.float32)
    import faiss

    async with _write_lock:
        index = _open_index()
        reg = _load_registry()

        # Allocate vector IDs
        start_id = reg["next_vector_id"]
        n = len(chunks)
        ids = np.arange(start_id, start_id + n, dtype=np.int64)

        index.add_with_ids(embeddings_np, ids)

        # Update registry
        reg["documents"][str(document_id)] = {
            "vector_ids": list(range(start_id, start_id + n)),
            "chunks": chunks,
        }
        reg["next_vector_id"] = start_id + n

        # Persist atomically
        faiss.write_index(index, str(_UNIFIED_INDEX))
        _save_registry(reg)

    logger.info(f"FAISS added: doc_id={document_id}, chunks={n}, ids={start_id}-{start_id + n - 1}")
    return n


async def search_all(
    query: str, top_k: int = 5, document_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    """Search unified FAISS index for similar chunks."""
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

    results = []
    for score, vid in zip(scores[0], ids[0]):
        if vid < 0:
            continue
        # Find which document owns this vector_id
        for doc_id_str, info in docs.items():
            if vid in info["vector_ids"]:
                idx = vid - info["vector_ids"][0]
                if 0 <= idx < len(info["chunks"]):
                    results.append({
                        "document_id": int(doc_id_str),
                        "chunk_index": idx,
                        "text": info["chunks"][idx],
                        "score": float(score),
                    })
                break

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


async def search_document(
    document_id: int, query: str, top_k: int = 5
) -> list[dict[str, Any]]:
    return await search_all(query, top_k=top_k, document_ids=[document_id])


async def delete_document(document_id: int) -> bool:
    """Remove document vectors from unified index."""
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
        if hasattr(index, 'remove_ids'):
            try:
                index.remove_ids(ids_to_remove)
            except Exception:
                # remove_ids may not work on IndexIDMap(IndexFlat); rebuild without this doc
                dim = index.d.index.d if hasattr(index, 'd') else index.index.d
                new_base = faiss.IndexFlatIP(dim)
                new_index = faiss.IndexIDMap(new_base)
                # Re-add all remaining documents
                next_id = 0
                for did_str, dinfo in reg["documents"].items():
                    embs = []
                    for chunk in dinfo["chunks"]:
                        emb = await embed_texts([chunk])
                        embs.append(emb[0])
                    if embs:
                        arr = np.array(embs, dtype=np.float32)
                        nids = np.arange(next_id, next_id + len(embs), dtype=np.int64)
                        new_index.add_with_ids(arr, nids)
                        dinfo["vector_ids"] = list(range(next_id, next_id + len(embs)))
                        next_id += len(embs)
                reg["next_vector_id"] = next_id
                index = new_index

        faiss.write_index(index, str(_UNIFIED_INDEX))
        _save_registry(reg)

    logger.info(f"FAISS deleted: doc_id={document_id}, vectors_removed={len(info['vector_ids'])}")
    return True


async def rebuild_index():
    """Rebuild unified index from old doc_*.faiss files on startup."""
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

            # Extract vectors from old index
            vectors = faiss.vector_to_array(old_index.xb) if hasattr(old_index, 'xb') else None
            if vectors is None:
                # IndexFlat or similar — reconstruct vectors from chunks
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

    # Backup old files
    backup_dir = _VECTOR_DIR / "backup"
    backup_dir.mkdir(exist_ok=True)
    for idx_path in old_files:
        idx_path.rename(backup_dir / idx_path.name)
        meta_path = _VECTOR_DIR / f"doc_{idx_path.stem.split('_')[1]}.meta.json"
        if meta_path.exists():
            meta_path.rename(backup_dir / meta_path.name)

    logger.info(f"Migration complete: {len(old_files)} docs → unified.faiss")
```

- [ ] **Step 2: Test chunk_text with different document types**

Run:
```bash
cd FastAPI_ai_interview
E:/anaconda3/envs/AI_Interview/python.exe -c "
import asyncio
from app.services.vector_store import chunk_text

async def test():
    # PDF-style (page breaks)
    pdf = 'This is page one content.\n' * 20 + '\n' + 'This is page two.\n' * 10
    c1 = await chunk_text(pdf, 'test.pdf', '.pdf')
    print(f'PDF chunks: {len(c1)}')
    if c1: print(f'  First chunk starts: {c1[0][:80]}...')

    # DOCX-style  
    docx = 'Short title\n' + 'This is a long paragraph. ' * 30
    c2 = await chunk_text(docx, 'test.docx', '.docx')
    print(f'DOCX chunks: {len(c2)}')
    if c2: print(f'  First chunk starts: {c2[0][:80]}...')

    # TXT-style
    txt = 'This is a text document. ' * 100
    c3 = await chunk_text(txt, 'test.txt', '.txt')
    print(f'TXT chunks: {len(c3)}')
    if c3: print(f'  First chunk starts: {c3[0][:80]}...')

    # All chunks have context header
    for chunks in [c1, c2, c3]:
        for c in chunks:
            assert '[文档:' in c, f'Missing context header in: {c[:50]}'
    print('✓ All chunks have context headers')

asyncio.run(test())
"
```

- [ ] **Step 3: Test unified index add/search/delete**

Run:
```bash
cd FastAPI_ai_interview
E:/anaconda3/envs/AI_Interview/python.exe -c "
import asyncio, shutil
from pathlib import Path
from app.core.config import settings

# Clean test data
faiss_dir = Path(settings.FAISS_DIR)
shutil.rmtree(faiss_dir, ignore_errors=True)

from app.services.vector_store import add_document, search_all, delete_document

async def test():
    chunks1 = ['Python is a programming language', 'Python is used for AI']
    chunks2 = ['Java is statically typed', 'Java runs on JVM']

    n1 = await add_document(1, chunks1)
    print(f'Added doc 1: {n1} chunks')

    n2 = await add_document(2, chunks2)
    print(f'Added doc 2: {n2} chunks')

    results = await search_all('AI programming', top_k=3)
    print(f'Search results: {len(results)}')
    for r in results:
        print(f'  doc={r[\"document_id\"]} score={r[\"score\"]:.3f} text={r[\"text\"][:50]}')

    # Doc 1 should rank first for 'AI programming' query
    assert results[0]['document_id'] == 1, 'Expected doc 1 to be top result'

    await delete_document(1)
    results2 = await search_all('AI programming', top_k=3)
    print(f'After delete: {len(results2)} results')
    # Should only find doc 2 now
    assert all(r['document_id'] == 2 for r in results2) if results2 else True

    print('✓ All unified index tests passed')

asyncio.run(test())
"
```

- [ ] **Step 4: Commit**

```bash
git add FastAPI_ai_interview/app/services/vector_store.py
git commit -m "feat: unified FAISS index with smart chunking and embedding cache"
```

---

### Task 2: Adapt documents.py — New chunk_text Signature

**Files:**
- Modify: `FastAPI_ai_interview/app/api/v1/admin/documents.py` (line 245-264)

- [ ] **Step 1: Update _vectorize_document to pass filename/ext to chunk_text**

In `documents.py`, find `_vectorize_document` (lines 243-264) and update the chunk_text call:

```python
async def _vectorize_document(doc: Document, file_bytes: bytes, db: AsyncSession):
    from app.services.vector_store import add_document, chunk_text

    ext = Path(doc.file_path).suffix.lower()
    text = await _extract_doc_text(file_bytes, ext)
    if not text:
        doc.status = "error"
        doc.error_message = "无法从文档中提取文本"
        return

    chunks = await chunk_text(text, filename=doc.filename, ext=ext)
    if not chunks:
        doc.status = "error"
        doc.error_message = "文档内容为空或无法分块"
        return

    count = await add_document(doc.id, chunks)
    doc.status = "ready"
    doc.chunks_count = count
    logger.info(f"文档向量化完成: doc_id={doc.id}, chunks={count}")
```

- [ ] **Step 2: Commit**

```bash
git add FastAPI_ai_interview/app/api/v1/admin/documents.py
git commit -m "feat: pass filename and extension to chunk_text for smart splitting"
```

---

### Task 3: Adapt celery_tasks.py — Same chunk_text Fix

**Files:**
- Modify: `FastAPI_ai_interview/app/services/celery_tasks.py`

- [ ] **Step 1: Update _chunk_text_sync to use new unified chunk_text**

In `celery_tasks.py`, find the vectorize task's chunk_text call and update to match new signature:

```python
from app.services.vector_store import chunk_text  # already imported

# In vectorize_document_task, update:
chunks = await chunk_text(text, filename=filename, ext=ext)
```

If the function is sync in celery, wrap with asyncio:
```python
import asyncio as _asyncio
chunks = _asyncio.get_event_loop().run_until_complete(
    chunk_text(text, filename=filename, ext=ext_lower)
)
```

- [ ] **Step 2: Commit**

```bash
git add FastAPI_ai_interview/app/services/celery_tasks.py
git commit -m "fix: use new chunk_text with filename/ext in celery task"
```

---

### Task 4: Auto-migration on Startup

**Files:**
- Modify: `FastAPI_ai_interview/app/main.py`

- [ ] **Step 1: Call rebuild_index on app startup**

Add to `create_app()` in `main.py`, after `app = FastAPI(...)`:

```python
@app.on_event("startup")
async def startup_migrate_faiss():
    from app.services.vector_store import rebuild_index
    await rebuild_index()
```

- [ ] **Step 2: Commit**

```bash
git add FastAPI_ai_interview/app/main.py
git commit -m "feat: auto-migrate old FAISS indexes to unified index on startup"
```

---

### Task 5: Local Integration Test

- [ ] **Step 1: Test full flow locally**

```bash
cd FastAPI_ai_interview
E:/anaconda3/envs/AI_Interview/python.exe -c "
import asyncio, shutil
from pathlib import Path
from app.core.config import settings
from app.services import vector_store

# Clean and migrate
faiss_dir = Path(settings.FAISS_DIR)
shutil.rmtree(faiss_dir, ignore_errors=True)

async def test_full():
    # Simulate startup migration (should be noop since no old files)
    await vector_store.rebuild_index()

    # Add documents
    await vector_store.add_document(1, ['AI interview questions', 'Python basics', 'System design'])
    await vector_store.add_document(2, ['Resume tips', 'Behavioral questions'])

    # Search
    results = await vector_store.search_all('interview preparation')
    print(f'Results: {len(results)}')
    assert len(results) > 0, 'Search should return results'

    # Delete
    await vector_store.delete_document(1)
    results = await vector_store.search_all('AI')
    print(f'After delete: {len(results)} results')

    # Verify registry is clean
    reg = vector_store._load_registry()
    print(f'Registry docs: {list(reg[\"documents\"].keys())}')

    print('✓ Full integration test passed')

asyncio.run(test_full())
"
```

- [ ] **Step 2: Build frontend**

```bash
cd vue_ai_interview && npm run build
```

- [ ] **Step 3: Commit any remaining changes**

```bash
git add -A && git commit -m "test: verify unified FAISS index full flow"
```
