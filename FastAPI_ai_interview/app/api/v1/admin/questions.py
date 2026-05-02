"""Admin question bank CRUD endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.core.exceptions import NotFoundException
from app.models.question import Question
from app.models.user import User
from app.schemas.question import (
    CreateQuestionRequest,
    QuestionListResponse,
    QuestionResponse,
    UpdateQuestionRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/questions", tags=["管理后台-题库"])


@router.post("", status_code=201)
async def create_question(
    req: CreateQuestionRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建题目。"""
    question = Question(
        stage=req.stage,
        position_tags=req.position_tags,
        difficulty=req.difficulty,
        type=req.type,
        question_text=req.question_text,
        dimensions=req.dimensions,
        scoring_points=[p.model_dump() for p in req.scoring_points],
        sample_answer=req.sample_answer,
        follow_up_hints=req.follow_up_hints,
        tags=req.tags,
        created_by=current_user.id,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)

    logger.info(f"题目创建成功: question_id={question.id}")
    return {"question_id": question.id, "created_at": question.created_at.isoformat()}


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    stage: str | None = None,
    position: str | None = None,
    difficulty: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """查询题目列表（支持筛选和分页）。"""
    page_size = min(page_size, 100)
    query = select(Question).where(Question.is_deleted == 0)
    count_query = select(func.count()).select_from(Question).where(Question.is_deleted == 0)

    if stage:
        query = query.where(Question.stage == stage)
        count_query = count_query.where(Question.stage == stage)
    if difficulty:
        query = query.where(Question.difficulty == difficulty)
        count_query = count_query.where(Question.difficulty == difficulty)
    if position:
        # Search in position_tags JSON array
        query = query.where(Question.position_tags.contains(position))
        count_query = count_query.where(Question.position_tags.contains(position))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(
        query.order_by(Question.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    questions = result.scalars().all()

    items = [
        QuestionResponse(
            id=q.id,
            stage=q.stage,
            position_tags=q.position_tags,
            difficulty=q.difficulty,
            type=q.type,
            question_text=q.question_text,
            dimensions=q.dimensions,
            scoring_points=q.scoring_points,
            sample_answer=q.sample_answer,
            follow_up_hints=q.follow_up_hints,
            tags=q.tags,
            is_deleted=bool(q.is_deleted),
            created_by=q.created_by,
            created_at=q.created_at,
            updated_at=q.updated_at,
        )
        for q in questions
    ]

    return QuestionListResponse(items=items, total=total, page=page, page_size=page_size)


@router.put("/{question_id}")
async def update_question(
    question_id: int,
    req: UpdateQuestionRequest,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新题目（部分更新）。"""
    result = await db.execute(
        select(Question).where(Question.id == question_id, Question.is_deleted == 0)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise NotFoundException("题目不存在")

    update_data = req.model_dump(exclude_unset=True)
    if "scoring_points" in update_data and update_data["scoring_points"] is not None:
        update_data["scoring_points"] = [p.model_dump() for p in update_data["scoring_points"]]

    for field, value in update_data.items():
        setattr(question, field, value)

    await db.commit()
    logger.info(f"题目更新成功: question_id={question_id}")
    return {"message": "更新成功"}


@router.delete("/{question_id}", status_code=204)
async def delete_question(
    question_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除题目（软删除）。"""
    result = await db.execute(
        select(Question).where(Question.id == question_id, Question.is_deleted == 0)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise NotFoundException("题目不存在")

    question.is_deleted = 1
    await db.commit()
    logger.info(f"题目已删除（软删除）: question_id={question_id}")


@router.post("/batch", status_code=201)
async def batch_create_questions(
    questions: list[CreateQuestionRequest],
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """批量导入题目。每个题目的结构同单条创建。"""
    created = 0
    errors = []

    for i, req in enumerate(questions):
        try:
            question = Question(
                stage=req.stage,
                position_tags=req.position_tags,
                difficulty=req.difficulty,
                type=req.type,
                question_text=req.question_text,
                dimensions=req.dimensions,
                scoring_points=[p.model_dump() for p in req.scoring_points],
                sample_answer=req.sample_answer,
                follow_up_hints=req.follow_up_hints,
                tags=req.tags,
                created_by=current_user.id,
            )
            db.add(question)
            created += 1
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    await db.commit()
    logger.info(f"批量导入完成: created={created}, errors={len(errors)}")
    return {"created": created, "total": len(questions), "errors": errors}
