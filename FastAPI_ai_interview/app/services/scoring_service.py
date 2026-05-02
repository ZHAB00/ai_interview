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
        )
        logger.info(f"评分完成: total_score={result.get('total_score')}")
        return result

    @staticmethod
    def aggregate_dimensions(answers: list[dict]) -> dict[str, Any]:
        """Aggregate scores across all answers into final dimension averages.

        Returns overall_score, dimensions map, and pass/fail determination.
        """
        from app.core.config import settings

        threshold = getattr(settings, "PASS_THRESHOLD", 60)
        dim_scores: dict[str, list[float]] = {d: [] for d in SCORING_DIMENSIONS}

        for ans in answers:
            dims = ans.get("dimensions_scores", {})
            for d in SCORING_DIMENSIONS:
                score = dims.get(d)
                if score is not None:
                    dim_scores[d].append(float(score))

        avg_dimensions = {}
        for d, scores in dim_scores.items():
            avg_dimensions[d] = round(sum(scores) / len(scores)) if scores else 0

        # Overall score: weighted average (excluding zero contribution from missing dimensions)
        all_scores = [s for scores in dim_scores.values() for s in scores]
        overall = round(sum(all_scores) / len(all_scores)) if all_scores else 0

        # Pass: every dimension above threshold
        lowest = min(avg_dimensions.values()) if avg_dimensions else 0
        passed = lowest >= threshold

        return {
            "overall_score": overall,
            "dimensions": avg_dimensions,
            "passed": passed,
            "threshold": threshold,
            "lowest_dimension": min(avg_dimensions, key=avg_dimensions.get) if avg_dimensions else "",
        }

        logger.info(
            f"维度聚合完成: overall={overall}, passed={passed}, "
            f"lowest={result.get('lowest_dimension')}={result['dimensions'].get(result['lowest_dimension'], 0)}"
        )
        return result

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
