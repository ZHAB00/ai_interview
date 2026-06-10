"""Question bank auto-feedback — saves high-quality LLM questions back to bank."""

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question

logger = logging.getLogger(__name__)

MIN_SCORE_THRESHOLD = 70


class QuestionFeedbackService:
    """After an interview with score >= 70, save generated questions back
    to the question bank with deduplication."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def maybe_save_questions(
        self,
        interview_id: int,
        conversation: list[dict],
        position: str,
        difficulty: str,
        overall_score: int,
    ) -> int:
        """Extract questions from conversation and save to bank. Returns count."""
        if overall_score < MIN_SCORE_THRESHOLD:
            logger.info(
                f"面试分数{overall_score}<{MIN_SCORE_THRESHOLD}，跳过题库回写"
            )
            return 0

        saved = 0
        for entry in conversation:
            if entry.get("pending_question"):
                continue
            if entry.get("type") == "coding_challenge":
                continue

            question_text = (entry.get("question_text") or "").strip()
            if len(question_text) < 10:
                continue

            if await self._is_duplicate(question_text):
                continue

            stage = entry.get("stage", "")
            dimensions = list(entry.get("dimensions_scores", {}).keys()) or [
                "技术深度", "沟通逻辑"
            ]

            skill_tags = entry.get("skill_tags", [])
            if not isinstance(skill_tags, list):
                skill_tags = []
            # Derive tags from position + skill_tags if empty
            tags = list(skill_tags) if skill_tags else []
            if position:
                tags.append(position)
            tags = list(set(tags))  # deduplicate

            question = Question(
                stage=stage,
                position_tags=[position],
                difficulty=difficulty,
                type="technical",
                question_text=question_text,
                dimensions=dimensions,
                scoring_points=[],
                source="auto",
                source_interview_id=interview_id,
                skill_tags=skill_tags,
                tags=tags,
            )
            self.db.add(question)
            saved += 1

        if saved > 0:
            await self.db.commit()
            logger.info(
                f"题库回写完成: interview_id={interview_id}, saved={saved}"
            )
        return saved

    async def _is_duplicate(self, text: str) -> bool:
        """Check if a semantically similar question already exists."""
        normalized = text.strip().lower()
        if len(normalized) < 10:
            return True

        # Exact match
        result = await self.db.execute(
            select(func.count()).select_from(Question).where(
                Question.question_text == text, Question.is_deleted == 0
            )
        )
        if result.scalar() > 0:
            return True

        # Trigram similarity against recent questions
        result = await self.db.execute(
            select(Question.question_text)
            .where(Question.is_deleted == 0)
            .limit(200)
        )
        existing_texts = [row[0] for row in result.all()]

        for existing in existing_texts:
            existing_norm = existing.strip().lower()
            if normalized in existing_norm or existing_norm in normalized:
                return True
            if _trigram_jaccard(normalized, existing_norm) > 0.8:
                return True

        return False


def _trigram_jaccard(a: str, b: str) -> float:
    """Jaccard similarity on character trigrams."""
    def trigrams(s: str) -> set[str]:
        return {s[i:i + 3] for i in range(len(s) - 2)}

    ta = trigrams(a)
    tb = trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
