"""Celery async tasks for document processing and scoring."""

import asyncio
import io
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.services.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def vectorize_document_task(self, document_id: int, file_path: str, file_ext: str) -> dict:
    """Async task: extract text, chunk, embed, and store in FAISS index.

    Runs in a Celery worker process. Uses synchronous DB operations
    since Celery tasks are synchronous by default.
    """
    logger.info(f"开始异步向量化: document_id={document_id}")

    # Import here to avoid circular imports at module level
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.document import Document

    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)

    try:
        # 1. Extract text from file
        file_bytes = Path(file_path).read_bytes()
        text = _extract_doc_text_sync(file_bytes, file_ext)
        if not text:
            _update_doc_status(engine, document_id, "error", "无法从文档中提取文本")
            return {"status": "error", "message": "无法从文档中提取文本"}

        # 2. Chunk text
        from pathlib import Path as _Path
        filename = _Path(file_path).name
        chunks = asyncio.run(chunk_text(text, filename=filename, ext=file_ext))
        if not chunks:
            _update_doc_status(engine, document_id, "error", "文档内容为空或无法分块")
            return {"status": "error", "message": "文档内容为空或无法分块"}

        # 3. Embed and store in FAISS (async, so we run in a new event loop)
        count = asyncio.run(_embed_and_store(document_id, chunks))
        if count == 0:
            _update_doc_status(engine, document_id, "error", "向量化失败")
            return {"status": "error", "message": "向量化失败"}

        # 4. Update document status
        _update_doc_status(engine, document_id, "ready", None, chunks_count=count)

        logger.info(f"异步向量化完成: document_id={document_id}, chunks={count}")
        return {"status": "ready", "chunks_count": count}

    except Exception as e:
        logger.error(f"异步向量化失败: document_id={document_id}, error={e}", exc_info=True)
        _update_doc_status(engine, document_id, "error", str(e))
        self.retry(exc=e)
        return {"status": "error", "message": str(e)}

    finally:
        engine.dispose()


def _update_doc_status(
    engine,
    document_id: int,
    status: str,
    error_message: str | None = None,
    chunks_count: int | None = None,
) -> None:
    """Update document status in the database."""
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models.document import Document

    with Session(engine) as session:
        values = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        if chunks_count is not None:
            values["chunks_count"] = chunks_count
        session.execute(
            update(Document).where(Document.id == document_id).values(**values)
        )
        session.commit()


def _extract_doc_text_sync(file_bytes: bytes, ext: str) -> str:
    """Extract text from various document formats (sync version)."""
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()

        elif ext == ".docx":
            from docx import Document as DocxDocument
            doc_file = DocxDocument(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc_file.paragraphs).strip()

        elif ext in (".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml"):
            return file_bytes.decode("utf-8", errors="replace")

        else:
            return file_bytes.decode("utf-8", errors="replace")

    except Exception as e:
        logger.error(f"文档文本提取失败: {e}")
        return ""




async def _embed_and_store(document_id: int, chunks: list[str]) -> int:
    """Embed chunks and store in FAISS index."""
    from app.services.vector_store import add_document, chunk_text
    return await add_document(document_id, chunks)
