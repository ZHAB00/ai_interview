"""Tests for ScoringAgent and ScoringService."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.scoring_service import ScoringService, SCORING_DIMENSIONS


MOCK_SCORE_RESULT = {
    "total_score": 78,
    "dimensions": {
        "技术深度": 75,
        "技术广度": 80,
        "工程化思维": 70,
        "沟通逻辑": 85,
        "项目经验匹配度": 80,
    },
    "strengths": ["基础知识扎实", "表达清晰"],
    "weaknesses": ["系统设计方面可以更深入"],
    "errors": [
        {
            "type": "depth_insufficient",
            "snippet": "GIL就是锁",
            "correction": "GIL是全局解释器锁，限制了同一时刻只有一个线程执行Python字节码",
            "suggestion": "建议详细解释GIL的影响和绕过方案",
        }
    ],
    "overall_comment": "整体表现良好，基础知识扎实但部分问题的深度可以加强。",
}


@pytest.fixture
def mock_scoring_llm():
    async def _handler(messages, **kwargs):
        return MOCK_SCORE_RESULT
    return AsyncMock(side_effect=_handler)


class TestScoringAgent:
    """Test the ScoringAgent independently."""

    @pytest.mark.asyncio
    async def test_score_answer(self, db_session: AsyncSession, mock_scoring_llm):
        """Test scoring a single answer with mocked LLM."""
        from app.agents.scoring_agent import ScoringAgent

        agent = ScoringAgent()

        with patch.object(agent, "llm_call_json", mock_scoring_llm):
            result = await agent.score_answer(
                question_text="请解释Python的GIL锁",
                user_answer="GIL就是全局解释器锁，它限制了多线程",
                scoring_points=[
                    {"point": "描述GIL是什么", "max_score": 20},
                    {"point": "解释影响", "max_score": 40},
                ],
                sample_answer="GIL即全局解释器锁...",
                stage="技术面",
                position="AI Agent开发工程师",
                difficulty="中级",
            )

        assert result["total_score"] == 78
        assert len(result["dimensions"]) == 5
        assert result["dimensions"]["技术深度"] == 75
        assert len(result["strengths"]) > 0
        assert len(result["errors"]) > 0
        assert result["errors"][0]["type"] in ("fact_error", "depth_insufficient")

    @pytest.mark.asyncio
    async def test_score_without_scoring_points(self, db_session: AsyncSession, mock_scoring_llm):
        """Test scoring when no scoring points are available."""
        from app.agents.scoring_agent import ScoringAgent

        agent = ScoringAgent()

        with patch.object(agent, "llm_call_json", mock_scoring_llm):
            result = await agent.score_answer(
                question_text="说说你的项目经验",
                user_answer="做过几个Python项目",
                stage="HR面",
                position="后端开发",
                difficulty="初级",
            )

        assert "total_score" in result
        assert "dimensions" in result


class TestScoringService:
    """Test the ScoringService."""

    @pytest.mark.asyncio
    async def test_score_answer_via_service(self, db_session: AsyncSession, mock_scoring_llm):
        """Test scoring through the service layer."""
        service = ScoringService(db_session)

        with patch.object(service.agent, "llm_call_json", mock_scoring_llm):
            result = await service.score_answer(
                question_text="请解释GIL",
                user_answer="GIL是全局解释器锁",
                stage="技术面",
                position="AI Agent开发工程师",
                difficulty="中级",
            )

        assert result["total_score"] == 78

    def test_aggregate_dimensions(self):
        """Test dimension score aggregation."""
        answers = [
            {
                "dimensions_scores": {
                    "技术深度": 85,
                    "技术广度": 80,
                    "工程化思维": 70,
                    "沟通逻辑": 90,
                    "项目经验匹配度": 75,
                },
                "score": 80,
            },
            {
                "dimensions_scores": {
                    "技术深度": 75,
                    "技术广度": 70,
                    "工程化思维": 65,
                    "沟通逻辑": 85,
                    "项目经验匹配度": 70,
                },
                "score": 73,
            },
        ]

        result = ScoringService.aggregate_dimensions(answers)

        assert "overall_score" in result
        assert "dimensions" in result
        assert "passed" in result
        assert "threshold" in result
        assert result["dimensions"]["技术深度"] == 80  # (85+75)/2
        assert result["dimensions"]["沟通逻辑"] == 88  # (90+85)/2 = 87.5 → 88

    def test_aggregate_empty(self):
        """Test aggregation with empty answers."""
        result = ScoringService.aggregate_dimensions([])
        assert result["overall_score"] == 0
        assert all(v == 0 for v in result["dimensions"].values())

    def test_build_answer_record(self):
        """Test building a structured answer record."""
        record = ScoringService.build_answer_record(
            question_id=1,
            question_text="什么是GIL?",
            user_answer="GIL是锁",
            stage="技术面",
            score_result=MOCK_SCORE_RESULT,
            audio_url="/uploads/audio/test.wav",
        )

        assert record["question_id"] == 1
        assert record["score"] == 78
        assert record["dimensions_scores"]["技术深度"] == 75
        assert len(record["errors"]) == 1
        assert record["user_audio_url"] == "/uploads/audio/test.wav"
        assert "answered_at" in record
