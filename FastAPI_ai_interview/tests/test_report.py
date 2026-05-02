"""Tests for ReportAgent and ReportGenerator."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

MOCK_REPORT_RESULT = {
    "overall_comment": "候选人在技术基础和沟通方面表现良好，但系统设计能力有提升空间。",
    "stage_summaries": [
        {
            "stage": "初筛",
            "summary": "基础素质良好，沟通流畅",
            "highlights": ["表达清晰"],
            "concerns": [],
        },
        {
            "stage": "技术面",
            "summary": "技术基础扎实",
            "highlights": ["Python功底好"],
            "concerns": ["架构设计深度不足"],
        },
    ],
    "resume_deduction": 5,
    "deduction_reason": "简历中缺少Agent相关项目经验",
    "improvement_suggestions": ["多看系统设计案例", "练习分布式系统设计"],
    "key_strengths": ["沟通能力强", "技术基础扎实"],
    "key_weaknesses": ["系统设计经验不足"],
}


@pytest.fixture
def mock_report_llm():
    async def _handler(messages, **kwargs):
        return MOCK_REPORT_RESULT
    return AsyncMock(side_effect=_handler)


class TestReportAgent:
    """Test the ReportAgent independently."""

    @pytest.mark.asyncio
    async def test_generate_report(self, mock_report_llm):
        """Test generating a report with mocked LLM."""
        from app.agents.report_agent import ReportAgent

        agent = ReportAgent()

        answers = [
            {
                "stage": "初筛",
                "question_text": "请做自我介绍",
                "user_answer_text": "我是张三...",
                "score": 80,
                "feedback": "表现良好",
            },
            {
                "stage": "技术面",
                "question_text": "什么是GIL?",
                "user_answer_text": "GIL是...",
                "score": 75,
                "feedback": "基础知识过关",
            },
        ]

        with patch.object(agent, "llm_call_json", mock_report_llm):
            result = await agent.generate_report(
                position="AI Agent开发工程师",
                difficulty="中级",
                answers=answers,
                position_match_score=70,
                match_feedback="技能匹配度一般",
            )

        assert "overall_comment" in result
        assert result["resume_deduction"] == 5
        assert len(result["stage_summaries"]) == 2
        assert len(result["improvement_suggestions"]) >= 2
        assert len(result["key_strengths"]) > 0


class TestReportGenerator:
    """Test the ReportGenerator service."""

    @pytest.mark.asyncio
    async def test_generate_and_persist(self, db_session: AsyncSession, mock_report_llm):
        """Test full report generation and DB persistence."""
        from app.models.interview import Interview
        from app.models.resume import Resume
        from app.models.user import User
        from app.services.report_generator import ReportGenerator

        # Setup data
        user = User(
            phone="13810000001", username="repotest", password_hash="x", role="candidate"
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resume = Resume(
            user_id=user.id,
            file_path="/tmp/r.pdf",
            parsed_data={"name": "测试"},
            position="AI Agent开发工程师",
            difficulty="中级",
            position_match_score=80,
            match_feedback="匹配",
        )
        db_session.add(resume)
        await db_session.commit()
        await db_session.refresh(resume)

        import json
        interview = Interview(
            user_id=user.id,
            resume_id=resume.id,
            position="AI Agent开发工程师",
            difficulty="中级",
            mode="full",
            status="completed",
            answers=json.dumps([
                {
                    "stage": "技术面",
                    "question_text": "什么是GIL?",
                    "user_answer_text": "GIL是锁",
                    "score": 78,
                    "dimensions_scores": {
                        "技术深度": 75,
                        "技术广度": 80,
                        "工程化思维": 70,
                        "沟通逻辑": 85,
                        "项目经验匹配度": 80,
                    },
                    "errors": [],
                    "strengths": [],
                    "weaknesses": [],
                    "feedback": "OK",
                    "answered_at": "2026-04-27T10:00:00Z",
                }
            ]),
        )
        db_session.add(interview)
        await db_session.commit()
        await db_session.refresh(interview)

        generator = ReportGenerator(db_session)

        with patch.object(generator.agent, "llm_call_json", mock_report_llm):
            report = await generator.generate(interview.id)

        assert report is not None
        assert report.status == "completed"
        assert report.report_data["resume_deduction"] == 5
        assert "dimensions" in report.report_data
        assert "stage_breakdown" in report.report_data

        # Verify interview updated
        await db_session.refresh(interview)
        assert interview.overall_score is not None
        assert interview.passed is not None
