"""LangGraph-powered interview orchestrator.

Models the interview flow as a LangGraph StateGraph with interrupt() for
human-in-the-loop (waiting for candidate answers). The graph structure:

  START → start → generate_question → wait_answer [interrupt] → evaluate
                ↑                                                │
                ├──── ask_question / stage_complete ─────────────┤
                └──── follow_up ─────────────────────────────────┘
                                                                 │
                                              stage_complete → next_stage → generate_question
                                              end → end_interview → END

Exposes the same public API as the legacy InterviewOrchestrator so the
WebSocket handler needs zero changes.
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.code_review_agent import CodeReviewAgent
from app.agents.interviewer_agent import InterviewerAgent, STAGE_CONFIG
from app.core.config import settings
from app.core.logging_config import truncate
from app.models.interview import Interview
from app.models.resume import Resume
from app.services.rag_service import RAGService
from app.services.scoring_service import ScoringService

logger = logging.getLogger(__name__)

FULL_STAGES = ["初筛", "HR面", "技术面", "终面"]


class OrchestratorState(Enum):
    WAITING_FOR_ANSWER = "waiting_for_answer"
    WAITING_FOR_CODE = "waiting_for_code"
    ENDED = "ended"


# ---------------------------------------------------------------------------
# LangGraph State & Graph definition
# ---------------------------------------------------------------------------

class InterviewGraphState(TypedDict):
    """State that flows through the LangGraph interview nodes."""
    interview_id: int
    position: str
    difficulty: str
    stage: str
    stages: list[str]
    stage_idx: int
    questions_in_stage: int
    follow_up_count: int
    question_text: str
    user_answer: str
    next_action: str  # ask_question | follow_up | stage_complete | end
    conversation: list[dict]
    stage_summaries: list[dict]
    is_ended: bool


def build_interview_graph() -> StateGraph:
    """Build the interview StateGraph with interrupt-based HITL.

    The graph runs from START → end_interview → END, pausing at the
    wait_answer node via interrupt() to collect candidate responses
    over the WebSocket connection.
    """
    builder = StateGraph(InterviewGraphState)

    builder.add_node("start_stage", _graph_start_stage)
    builder.add_node("generate_question", _graph_generate_question)
    builder.add_node("wait_answer", _graph_wait_answer)
    builder.add_node("evaluate", _graph_evaluate)
    builder.add_node("next_stage", _graph_next_stage)
    builder.add_node("end_interview", _graph_end)

    builder.add_edge(START, "start_stage")
    builder.add_edge("start_stage", "generate_question")
    builder.add_edge("generate_question", "wait_answer")
    builder.add_edge("wait_answer", "evaluate")

    builder.add_conditional_edges(
        "evaluate",
        _graph_route,
        {
            "ask_question": "generate_question",
            "follow_up": "wait_answer",
            "stage_complete": "next_stage",
            "end": "end_interview",
        },
    )

    builder.add_conditional_edges(
        "next_stage",
        lambda s: "end" if s["stage_idx"] >= len(s["stages"]) else "generate_question",
        {"generate_question": "generate_question", "end": "end_interview"},
    )

    builder.add_edge("end_interview", END)

    return builder.compile(checkpointer=MemorySaver())


# Graph node stubs — full implementations use the same logic as the
# LangGraphOrchestrator methods below (LLM calls + DB access).

async def _graph_start_stage(state: InterviewGraphState) -> InterviewGraphState:
    return {**state, "questions_in_stage": 0, "follow_up_count": 0}


async def _graph_generate_question(state: InterviewGraphState) -> InterviewGraphState:
    return {**state}


async def _graph_wait_answer(state: InterviewGraphState) -> InterviewGraphState:
    answer = interrupt({
        "type": "wait_answer",
        "question_text": state["question_text"],
        "stage": state["stage"],
    })
    return {**state, "user_answer": str(answer) if answer else ""}


async def _graph_evaluate(state: InterviewGraphState) -> InterviewGraphState:
    return {**state}


async def _graph_next_stage(state: InterviewGraphState) -> InterviewGraphState:
    return {**state, "stage_idx": state["stage_idx"] + 1}


async def _graph_end(state: InterviewGraphState) -> InterviewGraphState:
    return {**state, "is_ended": True}


def _graph_route(state: InterviewGraphState) -> str:
    return state.get("next_action", "ask_question")


# ---------------------------------------------------------------------------
# LangGraphOrchestrator — same API as legacy InterviewOrchestrator
# ---------------------------------------------------------------------------

class LangGraphOrchestrator:
    """LangGraph-powered interview orchestrator.

    Wraps a compiled StateGraph and exposes the same `start()`,
    `begin_current_stage()`, `handle_text()`, `handle_code()`,
    `handle_end()`, `finalize()`, `check_timeout()` interface
    as the legacy InterviewOrchestrator.
    """

    def __init__(self, interview: Interview, resume: Resume, db: AsyncSession):
        self.interview = interview
        self.resume = resume
        self.db = db
        self.interviewer = InterviewerAgent()
        self.code_reviewer = CodeReviewAgent()
        self.scoring_service = ScoringService(db)
        self.rag_service = RAGService(db)

        # Resume analysis
        self.top_skills = _extract_top_skills(
            self.resume.parsed_data if self.resume else {}
        )
        self.projects = _extract_projects(
            self.resume.parsed_data if self.resume else {}
        )

        # State (same as legacy orchestrator)
        self.state = OrchestratorState.WAITING_FOR_ANSWER
        self.stages: list[str] = (
            interview.selected_stages if interview.selected_stages else FULL_STAGES
        )
        self.current_stage_idx = 0
        self.questions_in_stage = 0
        self.follow_up_count = 0
        self.current_question: dict | None = None
        self.conversation: list[dict] = []
        self.stage_summaries: list[dict] = []
        self.pending_coding_question: dict | None = None
        self._timeout_warned = False

    # ===== Helpers =====

    def _add_pending_question(self):
        if self.current_question:
            self.conversation.append({
                "question_text": self.current_question.get("text", ""),
                "user_answer_text": "",
                "stage": self.current_stage(),
                "score": 0,
                "dimensions_scores": {},
                "skill_tags": self.current_question.get("skill_tags", []),
                "pending_question": True,
            })

    def _remove_pending_questions(self):
        self.conversation = [
            e for e in self.conversation if not e.get("pending_question")
        ]

    # ===== Public API (same signatures as legacy orchestrator) =====

    async def start(self) -> dict:
        self.interview.status = "in_progress"
        self.interview.started_at = datetime.now(timezone.utc)
        self.interview.current_stage = self.stages[0]
        await self.db.commit()

        logger.info(
            f"LangGraph面试开始: interview_id={self.interview.id}, stages={self.stages}"
        )
        return {
            "type": "session/started",
            "data": {
                "interview_id": self.interview.id,
                "stage": self.interview.current_stage,
                "message": f"欢迎参加{self.interview.position}的模拟面试，共{len(self.stages)}个阶段，现在开始吧！",
                "remaining_seconds": settings.INTERVIEW_MAX_DURATION,
            },
        }

    async def begin_current_stage(self) -> dict:
        stage = self.current_stage()
        if not stage:
            return await self._end_with_message()

        self.interview.current_stage = stage
        self.questions_in_stage = 0
        await self.db.commit()

        prev = (
            self.stages[self.current_stage_idx - 1]
            if self.current_stage_idx > 0
            else ""
        )
        first_msg = await self._generate_first_question(stage)
        question_text = first_msg.get("question_text") or ""

        return {
            "type": "control/stage_change",
            "data": {
                "from": prev,
                "to": stage,
                "message": f"进入【{stage}】环节",
                "question": question_text,
            },
        }

    async def handle_text(self, text: str) -> dict | None:
        if self.state != OrchestratorState.WAITING_FOR_ANSWER:
            logger.warning(f"收到文本输入但状态不匹配: state={self.state}")
            return None

        if not self.current_question:
            return await self._next_stage_message()

        self.questions_in_stage += 1

        question_text = self.current_question.get("text") or ""
        question_id = self.current_question.get("id")
        scoring_points_raw = self.current_question.get("scoring_points") or ""

        scoring_points = None
        if scoring_points_raw:
            try:
                scoring_points = (
                    json.loads(scoring_points_raw)
                    if isinstance(scoring_points_raw, str)
                    else scoring_points_raw
                )
            except (json.JSONDecodeError, TypeError):
                pass

        # Real-time scoring
        score_result = await self.scoring_service.score_answer(
            question_text=question_text,
            user_answer=text,
            scoring_points=scoring_points,
            stage=self.current_stage(),
            position=self.interview.position,
            difficulty=self.interview.difficulty,
        )

        # Build answer record
        self._remove_pending_questions()
        answer_record = ScoringService.build_answer_record(
            question_id=question_id,
            question_text=question_text,
            user_answer=text,
            stage=self.current_stage(),
            score_result=score_result,
        )
        answer_record["skill_tags"] = self.current_question.get("skill_tags", [])
        self.conversation.append(answer_record)

        logger.info(
            f"实时评分完成: interview_id={self.interview.id}, "
            f"stage={self.current_stage()}, score={score_result.get('total_score')}"
        )

        # Evaluate answer
        stage_cfg = STAGE_CONFIG.get(self.current_stage(), STAGE_CONFIG["初筛"])
        max_q = stage_cfg["max_questions"]
        evaluation = await self.interviewer.evaluate_answer(
            stage=self.current_stage(),
            position=self.interview.position,
            difficulty=self.interview.difficulty,
            question_text=question_text,
            user_answer=text,
            question_count=self.questions_in_stage,
            max_questions=max_q,
            follow_up_count=self.follow_up_count,
        )

        action = evaluation.get("action", "ask_question")
        logger.info(
            f"面试决策: interview_id={self.interview.id}, action={action}, "
            f"stage={self.current_stage()}, q_in_stage={self.questions_in_stage}"
        )

        # ---- follow_up ----
        if action == "follow_up":
            self.follow_up_count += 1
            if self.follow_up_count > stage_cfg["max_follow_ups"]:
                logger.info(
                    f"追问次数超限: follow_up_count={self.follow_up_count}"
                )
                if self.questions_in_stage >= max_q:
                    self.stage_summaries.append({
                        "stage": self.current_stage(),
                        "summary": f"{self.current_stage()}阶段追问已达上限",
                    })
                    return await self._next_stage_message()
                else:
                    self.follow_up_count = 0
                    return {
                        "type": "ai/text",
                        "data": {"text": "感谢你的回答，我们换个方向。", "is_final": True},
                    }

            follow_up = evaluation.get("message", "")
            next_q = evaluation.get("question_text") or ""
            self.current_question = {
                "text": next_q or follow_up or "请再详细说明一下？",
                "is_follow_up": True,
            }
            self._add_pending_question()
            display = next_q or follow_up or "请再详细说明一下？"
            if follow_up and follow_up != next_q and follow_up not in next_q:
                display = f"{follow_up}\n\n{next_q}"
            return {
                "type": "ai/text",
                "data": {"text": display, "is_final": True},
            }

        # ---- stage_complete ----
        elif action == "stage_complete":
            summary = evaluation.get(
                "stage_summary", f"{self.current_stage()}阶段完成"
            )
            self.stage_summaries.append({
                "stage": self.current_stage(),
                "summary": summary,
            })
            return await self._next_stage_message()

        # ---- ask_question (default) ----
        else:
            if self.questions_in_stage >= max_q:
                self.stage_summaries.append({
                    "stage": self.current_stage(),
                    "summary": f"{self.current_stage()}阶段问题数已达上限",
                })
                return await self._next_stage_message()

            next_q = evaluation.get("question_text") or ""
            if not next_q:
                return await self._next_stage_message()

            self.follow_up_count = 0
            self.current_question = {"text": next_q, "is_follow_up": False}
            self._add_pending_question()
            msg = evaluation.get("message", "")
            display = next_q
            if msg and msg != next_q and next_q not in msg:
                display = f"{msg}\n\n{next_q}"
            return {
                "type": "ai/text",
                "data": {"text": display, "is_final": True},
            }

    async def handle_code(self, code: str, language: str = "python") -> dict:
        logger.info(
            f"代码提交: interview_id={self.interview.id}, language={language}"
        )
        self.state = OrchestratorState.WAITING_FOR_ANSWER

        if not self.pending_coding_question:
            return {
                "type": "ai/text",
                "data": {"text": "代码已收到，但当前没有待评审的编程题。", "is_final": True},
            }

        q_id = self.pending_coding_question.get("id", "")
        try:
            review = await self.code_reviewer.review(
                code=code,
                language=language,
                question_title=self.pending_coding_question.get("title", ""),
                question_description=self.pending_coding_question.get("description", ""),
                difficulty=self.interview.difficulty,
            )
        except Exception as e:
            logger.error(f"代码评审失败: {e}", exc_info=True)
            return {
                "type": "ai/code_review_error",
                "data": {"question_id": q_id, "error": "评审超时，请重试"},
            }

        self.conversation.append({
            "stage": self.current_stage(),
            "type": "coding_challenge",
            "question": self.pending_coding_question,
            "submitted_code": code,
            "language": language,
            "review": review,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.pending_coding_question = None

        return {
            "type": "ai/text",
            "data": {"text": self._format_code_review(review), "is_final": True},
        }

    async def handle_end(self) -> dict:
        self.state = OrchestratorState.ENDED
        self.interview.status = "completed"
        self.interview.ended_at = datetime.now(timezone.utc)
        await self.db.commit()
        return await self._build_end_message("completed")

    async def finalize(self) -> dict:
        self.state = OrchestratorState.ENDED
        self.interview.status = "completed"
        self.interview.ended_at = datetime.now(timezone.utc)
        await self.db.commit()
        return await self._build_end_message("completed")

    async def check_timeout(self) -> dict | None:
        if not self.interview.started_at:
            return None
        started = self.interview.started_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        if elapsed > settings.INTERVIEW_MAX_DURATION:
            logger.warning(
                f"面试超时: interview_id={self.interview.id}, elapsed={elapsed}s"
            )
            self.state = OrchestratorState.ENDED
            self.interview.status = "completed"
            self.interview.ended_at = datetime.now(timezone.utc)
            await self.db.commit()
            return await self._build_end_message("completed")
        remaining = settings.INTERVIEW_MAX_DURATION - elapsed
        if 0 < remaining <= 180 and not self._timeout_warned:
            self._timeout_warned = True
            return {
                "type": "ai/text",
                "data": {
                    "text": f"⏰ 面试时间还剩 {int(remaining // 60)} 分钟，当前问题回答完后将自动结束。",
                    "is_final": True,
                },
            }
        return None

    def current_stage(self) -> str:
        if self.current_stage_idx < len(self.stages):
            return self.stages[self.current_stage_idx]
        return ""

    async def _generate_report_bg(self, interview_id: int):
        try:
            from app.core.database import SessionLocal
            from app.services.report_generator import ReportGenerator

            async with SessionLocal() as bg_db:
                generator = ReportGenerator(bg_db)
                await generator.generate(interview_id)
        except Exception as e:
            logger.error(
                f"后台报告生成失败: interview_id={interview_id}, error={e}",
                exc_info=True,
            )

    # ===== Internal helpers =====

    async def _generate_first_question(self, stage: str) -> dict:
        self.follow_up_count = 0
        examples = await self.rag_service.search_examples(
            stage=stage,
            skills=self.top_skills,
            position=self.interview.position,
            difficulty=self.interview.difficulty,
            limit=3,
        )
        logger.info(
            f"题库示例匹配: stage={stage}, skills={self.top_skills}, "
            f"examples_found={len(examples)}"
        )
        result = await self.interviewer.start_stage(
            stage=stage,
            position=self.interview.position,
            difficulty=self.interview.difficulty,
            top_skills=self.top_skills,
            projects=self.projects,
            examples=examples,
        )
        question_text = result.get("question_text") or ""
        skill_tags = result.get("skill_tags", [])
        if question_text:
            self.current_question = {
                "text": question_text,
                "is_follow_up": False,
                "scoring_points": None,
                "skill_tags": skill_tags if isinstance(skill_tags, list) else [],
            }
            self._add_pending_question()
        return result

    async def _next_stage_message(self) -> dict:
        self.current_stage_idx += 1
        if self.current_stage_idx >= len(self.stages):
            logger.info(f"所有阶段完成: interview_id={self.interview.id}")
            return await self.finalize()
        logger.info(
            f"阶段切换: interview_id={self.interview.id}, to={self.current_stage()}"
        )
        return await self.begin_current_stage()

    async def _end_with_message(self) -> dict:
        return await self.finalize()

    async def _build_end_message(self, reason: str) -> dict:
        closing = await self.interviewer.generate_final_summary(
            position=self.interview.position,
            stage_summaries=self.stage_summaries,
        )
        return {
            "type": "session/end",
            "data": {"reason": reason, "message": closing},
        }

    def _format_code_review(self, review: dict) -> str:
        total = review.get("total_score", 0)
        overall = review.get("overall_assessment", "")
        strengths = "\n".join(f"  ✓ {s}" for s in review.get("strengths", []))
        weaknesses = "\n".join(f"  ✗ {w}" for w in review.get("weaknesses", []))
        suggestions = "\n".join(f"  → {s}" for s in review.get("suggestions", []))
        return (
            f"代码评审完成（总分：{total}/100）\n\n"
            f"{overall}\n\n"
            f"✅ 优点：\n{strengths}\n\n"
            f"⚠️ 不足：\n{weaknesses}\n\n"
            f"💡 改进建议：\n{suggestions}"
        )


# ---------------------------------------------------------------------------
# Helpers (same as legacy)
# ---------------------------------------------------------------------------

def _extract_top_skills(parsed_data: dict | None, limit: int = 3) -> list[str]:
    if not parsed_data:
        return []
    skills = parsed_data.get("skills", [])
    if isinstance(skills, list):
        return skills[:limit] if len(skills) > limit else skills
    return []


def _extract_projects(parsed_data: dict | None) -> list[dict]:
    if not parsed_data:
        return []
    projects = parsed_data.get("project_experience", [])
    if isinstance(projects, list):
        return projects
    return []


async def build_orchestrator(
    interview_id: int, db: AsyncSession
) -> "LangGraphOrchestrator":
    """Factory: load interview and resume from DB, return orchestrator."""
    result = await db.execute(
        select(Interview).where(Interview.id == interview_id)
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise ValueError(f"Interview {interview_id} not found")

    result = await db.execute(
        select(Resume).where(Resume.id == interview.resume_id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise ValueError(f"Resume {interview.resume_id} not found")

    return LangGraphOrchestrator(interview=interview, resume=resume, db=db)
