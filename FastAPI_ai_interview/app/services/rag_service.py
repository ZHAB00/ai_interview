"""RAG service — question bank search for few-shot examples and document retrieval.

The question bank is used to find relevant examples to guide LLM question generation,
NOT to serve questions directly to candidates.
"""

import logging

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question
from app.services.vector_store import search_all as faiss_search

logger = logging.getLogger(__name__)


class RAGService:
    """Hybrid retrieval: question bank examples + document vector search."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_examples(
        self,
        stage: str,
        skills: list[str] | None = None,
        position: str | None = None,
        difficulty: str | None = None,
        limit: int = 3,
    ) -> list[dict]:
        """Search question bank for few-shot examples matching resume skills and stage.

        Priority: exact skill match > position match > stage-only match.
        Returns examples as dicts (question_text, scoring_points, follow_up_hints, etc.)
        to be injected into the LLM prompt.
        """
        conditions = [
            Question.stage == stage,
            Question.is_deleted == 0,
        ]
        if difficulty:
            conditions.append(Question.difficulty == difficulty)

        result = await self.db.execute(
            select(Question).where(*conditions).limit(limit * 3)
        )
        candidates = result.scalars().all()

        if not candidates:
            logger.info(f"题库无匹配示例: stage={stage}")
            return []

        # Score and rank by skill tag match
        skill_set = set(s.lower() for s in skills) if skills else set()
        position_lower = position.lower() if position else ""

        scored = []
        for q in candidates:
            score = 0
            # Skill match: each matching tag adds 10 points
            if skill_set and q.skill_tags:
                for tag in q.skill_tags:
                    if tag.lower() in skill_set or any(s in tag.lower() for s in skill_set):
                        score += 10
            # Position match: 5 points
            if position_lower and q.position_tags:
                for pt in q.position_tags:
                    if position_lower in pt.lower() or pt.lower() in position_lower:
                        score += 5
                        break
            # Difficulty exact match bonus: 3 points
            if difficulty and q.difficulty == difficulty:
                score += 3
            scored.append((score, q))

        scored.sort(key=lambda x: x[0], reverse=True)

        examples = []
        for score, q in scored[:limit]:
            examples.append({
                "question_text": q.question_text,
                "skill_tags": q.skill_tags or [],
                "difficulty": q.difficulty,
                "type": q.type,
                "scoring_points": q.scoring_points,
                "sample_answer": q.sample_answer,
                "follow_up_hints": q.follow_up_hints or [],
                "dimensions": q.dimensions,
                "match_score": score,
            })
            logger.debug(f"示例匹配: score={score}, text={q.question_text[:50]}...")

        return examples

    async def search_questions(
        self,
        stage: str,
        position: str,
        difficulty: str | None = None,
        question_type: str | None = None,
        limit: int = 10,
    ) -> list[Question]:
        """Search question bank by stage, position, and optional filters."""
        conditions = [
            Question.stage == stage,
            Question.is_deleted == 0,
        ]
        if difficulty:
            conditions.append(Question.difficulty == difficulty)
        if question_type:
            conditions.append(Question.type == question_type)

        result = await self.db.execute(
            select(Question)
            .where(*conditions)
            .limit(limit)
        )
        questions = result.scalars().all()

        matched = []
        for q in questions:
            if q.position_tags and position in q.position_tags:
                matched.append(q)
            elif q.position_tags and any(
                tag in position or position in tag for tag in q.position_tags
            ):
                matched.append(q)

        return matched if matched else questions

    async def search_documents(self, query: str, top_k: int = 3) -> list[dict]:
        """Search knowledge base documents via FAISS vector similarity."""
        try:
            results = await faiss_search(query, top_k=top_k)
            return results
        except Exception as e:
            logger.warning(f"FAISS 检索失败: {e}")
            return []

    async def get_context_for_interview(
        self,
        query: str,
        stage: str,
        position: str,
        difficulty: str | None = None,
        top_k_questions: int = 5,
        top_k_docs: int = 3,
    ) -> dict:
        """Get combined context from both question bank and knowledge documents.

        Returns a dict with 'questions' and 'documents' keys for injection
        into the interviewer agent's prompt.
        """
        questions = await self.search_questions(
            stage=stage,
            position=position,
            difficulty=difficulty,
            limit=top_k_questions,
        )

        docs = await self.search_documents(query, top_k=top_k_docs)

        return {
            "questions": [
                {
                    "id": q.id,
                    "text": q.question_text,
                    "type": q.type,
                    "scoring_points": q.scoring_points,
                    "sample_answer": q.sample_answer,
                }
                for q in questions
            ],
            "documents": docs,
        }

    async def get_question_by_id(self, question_id: int) -> Question | None:
        """Fetch a specific question from the bank."""
        result = await self.db.execute(
            select(Question).where(
                Question.id == question_id,
                Question.is_deleted == 0,
            )
        )
        return result.scalar_one_or_none()
