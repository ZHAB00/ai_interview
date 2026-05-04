"""Application entry point.

Start server:    python -m app.main
Seed questions:  python -m app.main --seed
"""

import asyncio
import logging
import sys

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.responses import FileResponse
from jwt import PyJWTError as JWTError

from app.api.v1.auth import router as auth_router
from app.api.v1.resumes import router as resume_router
from app.api.v1.interviews import router as interview_router
from app.api.v1.admin.questions import router as admin_questions_router
from app.api.v1.admin.documents import router as admin_documents_router
from app.api.v1.admin.users import router as admin_users_router
from app.api.v1.captcha import router as captcha_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.messages import router as messages_router
from app.core.config import settings
from app.core.exceptions import EXCEPTION_HANDLERS
from app.core.logging_config import logging_setup, suppress_startup_duplicate
from app.core.middleware import setup_middleware
from app.core.security import decode_token

# Initialize logging
import logging as _logging
logging_setup(
    level=getattr(_logging, settings.LOG_LEVEL.upper(), _logging.INFO),
    fmt=settings.LOG_FORMAT,
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        exception_handlers=EXCEPTION_HANDLERS,
    )

    # Setup middleware
    setup_middleware(app)

    # Register REST routers
    app.include_router(auth_router)
    app.include_router(resume_router)
    app.include_router(interview_router)
    app.include_router(admin_questions_router)
    app.include_router(admin_documents_router)
    app.include_router(admin_users_router)
    app.include_router(captcha_router)
    app.include_router(feedback_router)
    app.include_router(messages_router)

    # Serve audio / documents via authenticated download (resumes & FAISS are never exposed)
    upload_dir = Path(settings.UPLOAD_DIR)

    @app.get("/uploads/{sub}/{filename}")
    async def serve_upload_file(sub: str, filename: str, token: str = Query(...)):
        try:
            decode_token(token)
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        # Prevent path traversal
        safe_name = Path(filename).name
        if safe_name != filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        if sub not in ("audio", "documents"):
            raise HTTPException(status_code=404, detail="Not found")

        file_path = upload_dir / sub / safe_name
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(file_path)

    # WebSocket endpoint
    @app.websocket("/ws/interview/{interview_id}")
    async def ws_interview(
        websocket: WebSocket,
        interview_id: int,
        token: str = Query(...),
    ):
        from app.ws.interview_ws import interview_handler
        await interview_handler(websocket, interview_id, token)

    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "app": settings.APP_NAME}

    return app


app = create_app()


async def seed_questions_cli():
    """Seed the question bank via CLI: python -m app.services.seed_questions"""
    from app.core.database import SessionLocal
    from app.services.seed_questions import seed_questions

    async with SessionLocal() as db:
        count = await seed_questions(db)
        print(f"预置题目完成: 新增 {count} 道题目")


if __name__ == "__main__":
    if "--seed" in sys.argv:
        asyncio.run(seed_questions_cli())
    else:
        logger.info(f"启动服务: http://0.0.0.0:{settings.APP_PORT}")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=settings.APP_PORT,
            reload=settings.DEBUG,
        )
