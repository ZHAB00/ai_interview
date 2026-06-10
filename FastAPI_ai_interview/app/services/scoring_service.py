"""Scoring service - orchestrates answer scoring and dimension aggregation."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.scoring_agent import ScoringAgent, SCORING_DIMENSIONS
from app.core.logging_config import truncate

logger = logging.getLogger(__name__)


class ScoringService:
    """Service for scoring interview answers and aggregating dimension scores.

    Scores each answer in real-time via ScoringAgent, stores scores in the
    interview answers JSON, and aggregates dimension scores for final reports.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = ScoringAgent()

    async def score_answer(
        self,
        question_text: str,
        user_answer: str,
        scoring_points: list[dict] | None = None,
        sample_answer: str | None = None,
        stage: str = "",
        position: str = "",
        difficulty: str = "中级",
        kb_documents: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Score a single answer and return structured evaluation."""
        logger.info(
            f"评分开始: stage={stage}, question={truncate(question_text)}, "
            f"answer_len={len(user_answer)}"
        )
        result = await self.agent.score_answer(
            question_text=question_text,
            user_answer=user_answer,
            scoring_points=scoring_points,
            sample_answer=sample_answer,
            stage=stage,
            position=position,
            difficulty=difficulty,
            kb_documents=kb_documents,
        )
        logger.info(f"评分完成: total_score={result.get('total_score')}")
        return result

    @staticmethod
    def aggregate_dimensions(answers: list[dict]) -> dict[str, Any]:
        """Aggregate answers with topic-based weighting.

        Each topic = one main question + its follow-ups.
        Topic score = main_score * 0.6 + avg_follow_up_score * 0.4.
        No follow-ups → topic score = main_score (100%).
        Overall = average of all topic scores.
        Dimensions = simple average across all answers (no weighting).
        Legacy answers (no is_follow_up field) form individual topics.
        """
        from app.core.config import settings

        threshold = getattr(settings, "PASS_THRESHOLD", 60)

        # --- Group into topics ---
        topics: list[list[dict]] = []
        current: list[dict] = []
        for ans in answers:
            if ans.get("pending_question"):
                continue
            # None (legacy) or False = new topic
            if not ans.get("is_follow_up"):
                if current:
                    topics.append(current)
                current = [ans]
            else:
                current.append(ans)
        if current:
            topics.append(current)

        # --- Compute topic scores + dimension averages ---
        dim_scores: dict[str, list[float]] = {d: [] for d in SCORING_DIMENSIONS}
        topic_totals: list[float] = []

        for topic in topics:
            main_score = 0.0
            fu_scores: list[float] = []

            for ans in topic:
                score = ans.get("score", 0)
                if ans.get("is_follow_up"):
                    fu_scores.append(float(score))
                else:
                    main_score = float(score)

                dims = ans.get("dimensions_scores", {})
                for d in SCORING_DIMENSIONS:
                    val = dims.get(d)
                    if val is not None:
                        dim_scores[d].append(float(val))

            # Weighted topic total: main 60% + fu_avg 40%
            if fu_scores:
                fu_avg = sum(fu_scores) / len(fu_scores)
                topic_total = round(main_score * 0.6 + fu_avg * 0.4)
            else:
                topic_total = round(main_score)

            topic_totals.append(topic_total)

        # --- Averages ---
        avg_dimensions = {}
        for d, scores in dim_scores.items():
            avg_dimensions[d] = round(sum(scores) / len(scores)) if scores else 0

        overall = round(sum(topic_totals) / len(topic_totals)) if topic_totals else 0

        lowest = min(avg_dimensions.values()) if avg_dimensions else 0
        passed = overall >= threshold and lowest >= threshold

        logger.info(
            f"加权评分: topics={len(topic_totals)}, totals={topic_totals}, "
            f"overall={overall}, passed={passed}"
        )
        return {
            "overall_score": overall,
            "dimensions": avg_dimensions,
            "passed": passed,
            "threshold": threshold,
            "topic_count": len(topic_totals),
            "lowest_dimension": min(avg_dimensions, key=avg_dimensions.get) if avg_dimensions else "",
        }

    @staticmethod
    def build_answer_record(
        question_id: int | None,
        question_text: str,
        user_answer: str,
        stage: str,
        score_result: dict[str, Any],
        audio_url: str | None = None,
    ) -> dict[str, Any]:
        """Build a structured answer record for storage in interviews.answers."""
        return {
            "question_id": question_id,
            "question_text": question_text,
            "stage": stage,
            "user_answer_text": user_answer,
            "user_audio_url": audio_url,
            "score": score_result.get("total_score", 0),
            "dimensions_scores": score_result.get("dimensions", {}),
            "feedback": score_result.get("overall_comment", ""),
            "strengths": score_result.get("strengths", []),
            "weaknesses": score_result.get("weaknesses", []),
            "errors": score_result.get("errors", []),
            "answered_at": datetime.now(timezone.utc).isoformat(),
        }
