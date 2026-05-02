"""Resume endpoints: upload/parse and retrieve."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import FileTooLargeException, NotFoundException, ValidationErrorException
from app.core.config import settings
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeDetailResponse, ResumeUploadResponse
from app.services.resume_parser import parse_resume

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resumes", tags=["简历"])

# Allowed extensions and magic bytes for resume uploads
_RESUME_MAGIC = {
    ".pdf":  b"%PDF",
    ".docx": b"PK\x03\x04",
    ".png":  b"\x89PNG",
    ".jpg":  b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
}


def _check_file_magic(filename: str, data: bytes, allowed: dict[str, bytes]) -> None:
    """Validate file content matches its claimed extension via magic bytes."""
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise ValidationErrorException(f"不支持的文件类型: {ext}")
    expected = allowed[ext]
    if data[:len(expected)] != expected:
        raise ValidationErrorException(f"文件内容与扩展名 {ext} 不匹配，请上传正确的文件")


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    position: str = Form(...),
    difficulty: str = Form(default="中级"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传并解析简历。同步解析，等待解析完成再返回。"""
    # Validate file
    if not file.filename:
        raise ValidationErrorException("文件名为空")

    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE:
        raise FileTooLargeException("文件大小超过 10MB 限制")

    _check_file_magic(file.filename, file_bytes, _RESUME_MAGIC)

    # Parse resume
    parsed_data, saved_path = await parse_resume(file_bytes, file.filename, position)

    # Save to database
    resume = Resume(
        user_id=current_user.id,
        file_path=saved_path,
        parsed_data=parsed_data,
        position=position,
        difficulty=difficulty,
        position_match_score=parsed_data.get("position_match_score"),
        match_feedback=parsed_data.get("match_feedback"),
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)

    logger.info(f"简历上传并解析成功: resume_id={resume.id}, user_id={current_user.id}")
    return ResumeUploadResponse(
        resume_id=resume.id,
        parsed_data=parsed_data,
        position_match_score=resume.position_match_score,
        match_feedback=resume.match_feedback,
    )


@router.get("/{resume_id}", response_model=ResumeDetailResponse)
async def get_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取简历详情。"""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise NotFoundException("简历不存在")

    return ResumeDetailResponse(
        id=resume.id,
        user_id=resume.user_id,
        file_path=resume.file_path,
        parsed_data=resume.parsed_data,
        position=resume.position,
        difficulty=resume.difficulty,
        position_match_score=resume.position_match_score,
        match_feedback=resume.match_feedback,
        uploaded_at=resume.uploaded_at,
    )
