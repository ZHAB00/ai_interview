"""Report generator - orchestrates final report creation after interview ends."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.report_agent import ReportAgent
from app.models.interview import Interview
from app.models.report import Report
from app.models.resume import Resume
from app.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates the final interview report.

    Orchestrates ReportAgent to produce a comprehensive report including
    dimension scores, stage breakdowns, resume deductions, and recommendations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = ReportAgent()

    async def generate(self, interview_id: int) -> Report:
        """Generate the full report for a completed interview."""
        # Load interview
        result = await self.db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise ValueError(f"Interview {interview_id} not found")

        # Load resume
        result = await self.db.execute(
            select(Resume).where(Resume.id == interview.resume_id)
        )
        resume = result.scalar_one_or_none()

        # Parse answers
        answers: list[dict] = []
        if interview.answers:
            try:
                answers = json.loads(interview.answers) if isinstance(interview.answers, str) else interview.answers
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse answers JSON for interview {interview_id}")

        # Aggregate dimension scores
        text_answers = [a for a in answers if not a.get("type") and not a.get("pending_question")]  # exclude coding + pending
        aggregation = ScoringService.aggregate_dimensions(text_answers)

        # Generate narrative report via ReportAgent.
        # If the resume was uploaded for a different position than this interview,
        # discard the stale match_feedback — it references the wrong position.
        if resume and resume.position and resume.position != interview.position:
            match_score = None
            match_fb = None
        else:
            match_score = resume.position_match_score if resume else None
            match_fb = resume.match_feedback if resume else None

        narrative = await self.agent.generate_report(
            position=interview.position,
            difficulty=interview.difficulty,
            answers=text_answers,
            position_match_score=match_score,
            match_feedback=match_fb,
            jd_analysis=interview.jd_analysis,
        )

        # Build stage breakdown
        stage_breakdown = self._build_stage_breakdown(answers, narrative.get("stage_summaries", []))

        # Calculate final score
        overall_score = aggregation["overall_score"]
        resume_deduction = narrative.get("resume_deduction", 0)
        final_score = max(0, overall_score - resume_deduction)

        from app.core.config import settings
        threshold = getattr(settings, "PASS_THRESHOLD", 60)
        # Pass: overall above threshold AND no dimension below threshold
        overall_passed = final_score >= threshold
        dimensions_passed = all(v >= threshold for v in aggregation["dimensions"].values())

        report_data = {
            "overall_score": final_score,
            "passed": overall_passed and dimensions_passed,
            "threshold": threshold,
            "dimensions": aggregation["dimensions"],
            "stage_breakdown": stage_breakdown,
            "resume_deduction": resume_deduction,
            "deduction_reason": narrative.get("deduction_reason", ""),
            "overall_comment": narrative.get("overall_comment", ""),
            "key_strengths": narrative.get("key_strengths", []),
            "key_weaknesses": narrative.get("key_weaknesses", []),
            "improvement_suggestions": narrative.get("improvement_suggestions", []),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Upsert report (with retry for concurrent race)
        try:
            result = await self.db.execute(
                select(Report).where(Report.interview_id == interview_id)
            )
            report = result.scalar_one_or_none()

            if report:
                report.report_data = report_data
                report.status = "completed"
                report.updated_at = datetime.now(timezone.utc)
            else:
                report = Report(
                    interview_id=interview_id,
                    report_data=report_data,
                    status="completed",
                )
                self.db.add(report)
                await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            # Another task already inserted — load and update
            result = await self.db.execute(
                select(Report).where(Report.interview_id == interview_id)
            )
            report = result.scalar_one()
            report.report_data = report_data
            report.status = "completed"
            report.updated_at = datetime.now(timezone.utc)

        # Update interview scores
        interview.overall_score = final_score
        interview.passed = 1 if (overall_passed and dimensions_passed) else 0
        interview.resume_deduction = resume_deduction
        interview.deduction_reason = narrative.get("deduction_reason", "")

        await self.db.commit()
        logger.info(f"报告生成完成: interview_id={interview_id}, score={final_score}")

        # Auto-feedback: save high-quality LLM questions back to question bank
        try:
            from app.services.question_feedback_service import QuestionFeedbackService
            feedback_svc = QuestionFeedbackService(self.db)
            saved = await feedback_svc.maybe_save_questions(
                interview_id=interview_id,
                conversation=answers if isinstance(answers, list) else [],
                position=interview.position,
                difficulty=interview.difficulty,
                overall_score=final_score,
            )
            if saved > 0:
                logger.info(f"题库回写: interview_id={interview_id}, saved={saved} questions")
        except Exception as e:
            logger.error(f"题库回写失败: {e}", exc_info=True)

        return report

    def _build_stage_breakdown(
        self, answers: list[dict], stage_summaries: list[dict]
    ) -> list[dict]:
        """Build stage-by-stage breakdown from answers."""
        stages: dict[str, list[dict]] = {}
        for a in answers:
            stage = a.get("stage", "未知")
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(a)

        breakdown = []
        for stage_name, stage_answers in stages.items():
            summary = next(
                (s for s in stage_summaries if s.get("stage") == stage_name), {}
            )
            breakdown.append({
                "stage": stage_name,
                "summary": summary.get("summary", ""),
                "highlights": summary.get("highlights", []),
                "concerns": summary.get("concerns", []),
                "questions": [
                    {
                        "question_text": a.get("question_text", ""),
                        "user_answer_summary": (a.get("user_answer_text", "")[:200] + "...")
                        if len(a.get("user_answer_text", "")) > 200
                        else a.get("user_answer_text", ""),
                        "score": a.get("score", 0),
                        "dimensions_scores": a.get("dimensions_scores", {}),
                        "user_audio_url": a.get("user_audio_url", ""),
                        "strengths": a.get("strengths", []),
                        "weaknesses": a.get("weaknesses", []),
                        "errors": a.get("errors", []),
                    }
                    for a in stage_answers
                    if not a.get("type") and not a.get("pending_question")  # skip coding + pending
                ],
            })

        return breakdown
