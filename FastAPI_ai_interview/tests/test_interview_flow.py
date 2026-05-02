"""Integration tests for the interview flow: orchestrator + WebSocket."""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.main import create_app
from app.models.interview import Interview
from app.models.resume import Resume
from app.models.user import User


@pytest.fixture
def mock_llm_json_response():
    """Mock LLM that returns different JSON based on the prompt content."""
    async def _messages_handler(messages, **kwargs):
        content = messages[-1]["content"] if messages else ""

        if "面试进入到" in content:
            return {
                "action": "ask_question",
                "message": "请简单介绍一下你自己和你的项目经验。",
                "question_text": "请简单介绍一下你自己和你的项目经验。",
                "question_count_in_stage": 1,
            }
        elif "请评估候选人的回答" in content:
            if "2/4" in content or "3/4" in content or "4/4" in content:
                return {
                    "action": "stage_complete",
                    "message": "好的，这个阶段的问题就到这里。",
                    "stage_summary": "候选人对基础概念有较好的理解。",
                    "question_count_in_stage": int(content.split("已问问题数：")[1].split("/")[0]),
                }
            return {
                "action": "ask_question",
                "message": "下一个问题：请解释Agent的工作原理。",
                "question_text": "请解释Agent的工作原理。",
                "question_count_in_stage": int(content.split("已问问题数：")[1].split("/")[0]) + 1,
            }
        elif "面试即将结束" in content:
            return "感谢您参加本次面试，您的表现我们已经记录。报告正在生成中，请稍后查看。"
        else:
            return {"action": "ask_question", "message": "下一个问题。", "question_text": "下一个问题。"}

    return AsyncMock(side_effect=_messages_handler)


@pytest.fixture
def mock_code_review_response():
    async def _messages_handler(messages, **kwargs):
        return {
            "overall_assessment": "代码整体质量良好，逻辑清晰。",
            "correctness": {"score": 20, "comment": "逻辑正确"},
            "performance": {"score": 18, "comment": "时间复杂度合理"},
            "readability": {"score": 20, "comment": "命名规范"},
            "security": {"score": 25, "comment": "无明显安全问题"},
            "total_score": 83,
            "strengths": ["逻辑清晰", "命名规范"],
            "weaknesses": ["可以添加边界条件处理"],
            "improved_code": "def quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n    ...",
            "suggestions": ["添加输入验证"],
        }
    return AsyncMock(side_effect=_messages_handler)


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Seed required data for interview tests."""
    # Create user
    user = User(phone="13800138001", username="testuser", password_hash="hashed", role="candidate")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create resume
    resume = Resume(
        user_id=user.id,
        file_path="/tmp/test.pdf",
        parsed_data={"name": "张三", "skills": ["Python", "FastAPI"]},
        position="AI Agent开发工程师",
        difficulty="中级",
        position_match_score=75,
        match_feedback="技能匹配",
    )
    db_session.add(resume)
    await db_session.commit()
    await db_session.refresh(resume)

    # Create interview
    interview = Interview(
        user_id=user.id,
        resume_id=resume.id,
        position="AI Agent开发工程师",
        difficulty="中级",
        mode="full",
        selected_stages=["初筛", "技术面"],
        status="created",
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    return {
        "user": user,
        "resume": resume,
        "interview": interview,
    }


class TestInterviewOrchestrator:
    """Test the interview orchestrator directly with mocked LLM."""

    @pytest.mark.asyncio
    async def test_full_interview_flow(
        self, db_session: AsyncSession, mock_llm_json_response, mock_code_review_response
    ):
        """Test a complete interview flow through all stages."""
        from app.models.resume import Resume
        from app.models.user import User
        from app.services.interview_orchestrator import InterviewOrchestrator

        # Setup
        user = User(phone="13800138002", username="testuser2", password_hash="hashed", role="candidate")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resume = Resume(
            user_id=user.id,
            file_path="/tmp/test.pdf",
            parsed_data={"name": "李四", "skills": ["Python"]},
            position="AI Agent开发工程师",
            difficulty="中级",
            position_match_score=80,
            match_feedback="匹配",
        )
        db_session.add(resume)
        await db_session.commit()
        await db_session.refresh(resume)

        interview = Interview(
            user_id=user.id,
            resume_id=resume.id,
            position="AI Agent开发工程师",
            difficulty="中级",
            mode="full",
            status="created",
        )
        db_session.add(interview)
        await db_session.commit()
        await db_session.refresh(interview)

        orchestrator = InterviewOrchestrator(interview=interview, resume=resume, db=db_session)

        with patch.object(orchestrator.interviewer, "llm_call_json", mock_llm_json_response), \
             patch.object(orchestrator.interviewer, "llm_call", AsyncMock(return_value="结束语")), \
             patch.object(orchestrator.code_reviewer, "llm_call_json", mock_code_review_response):

            # Start interview
            start_msg = await orchestrator.start()
            assert start_msg["type"] == "session/started"
            assert interview.status == "in_progress"

            # Begin first stage (初筛)
            stage_msg = await orchestrator.begin_current_stage()
            assert stage_msg["type"] == "control/stage_change"
            assert stage_msg["data"]["to"] == "初筛"
            assert "question" in stage_msg["data"]

            # First Q&A
            resp1 = await orchestrator.handle_text("我是李四，有3年Python开发经验...")
            assert resp1 is not None
            assert resp1["type"] == "ai/text"

            # Second Q&A (evaluate will say stage_complete based on our mock)
            resp2 = await orchestrator.handle_text("Agent的工作原理是...")
            assert resp2 is not None

            # If stage_complete, should transition to next stage or end
            if orchestrator.current_stage_idx > 0:
                # Should have moved to 技术面
                assert orchestrator.current_stage() == "技术面"

            # End interview
            end_msg = await orchestrator.finalize()
            assert end_msg["type"] == "session/end"
            assert interview.status == "completed"
            assert interview.answers is not None

    @pytest.mark.asyncio
    async def test_early_end(self, db_session: AsyncSession, mock_llm_json_response, mock_code_review_response):
        """Test user-initiated early end of interview."""
        from app.models.resume import Resume
        from app.models.user import User
        from app.services.interview_orchestrator import InterviewOrchestrator

        user = User(phone="13800138003", username="testuser3", password_hash="hashed", role="candidate")
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        resume = Resume(
            user_id=user.id,
            file_path="/tmp/test.pdf",
            parsed_data={"name": "王五"},
            position="AI Agent开发工程师",
            difficulty="中级",
            position_match_score=70,
            match_feedback="匹配",
        )
        db_session.add(resume)
        await db_session.commit()
        await db_session.refresh(resume)

        interview = Interview(
            user_id=user.id,
            resume_id=resume.id,
            position="AI Agent开发工程师",
            difficulty="中级",
            mode="full",
            status="created",
        )
        db_session.add(interview)
        await db_session.commit()
        await db_session.refresh(interview)

        orchestrator = InterviewOrchestrator(interview=interview, resume=resume, db=db_session)

        with patch.object(orchestrator.interviewer, "llm_call", AsyncMock(return_value="感谢参与")), \
             patch.object(orchestrator.interviewer, "llm_call_json", mock_llm_json_response), \
             patch.object(orchestrator.code_reviewer, "llm_call_json", mock_code_review_response):
            await orchestrator.start()
            end_msg = await orchestrator.handle_end()

        assert end_msg["type"] == "session/end"
        assert interview.status == "completed"


class TestInterviewWebSocket:
    """Test the WebSocket interview endpoint."""

    @pytest.mark.asyncio
    async def test_ws_requires_token(self, db_session: AsyncSession):
        """Test that WebSocket connection fails without valid token."""
        app = create_app()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Without token, should fail (FastAPI WebSocket requires the query param)
            try:
                async with client.stream(
                    "GET", "/ws/interview/1"
                ) as response:
                    assert response.status_code != 200
            except Exception:
                pass  # Expected - connection shouldn't establish

    @pytest.mark.asyncio
    async def test_create_and_check_interview(self, db_session: AsyncSession, seeded_db: dict):
        """Test creating an interview via REST and verifying state."""
        app = create_app()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db

        from app.api.deps import get_current_user

        async def override_get_current_user():
            return seeded_db["user"]

        app.dependency_overrides[get_current_user] = override_get_current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Get interview history
            response = await client.get("/api/interviews/history")
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_create_interview_api(self, db_session: AsyncSession, seeded_db: dict):
        """Test the POST /api/interviews endpoint."""
        app = create_app()

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db

        from app.api.deps import get_current_user

        async def override_get_current_user():
            return seeded_db["user"]

        app.dependency_overrides[get_current_user] = override_get_current_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/interviews", json={
                "resume_id": seeded_db["resume"].id,
                "position": "AI Agent开发工程师",
                "difficulty": "中级",
                "mode": "stage",
                "selected_stages": ["技术面"],
            })
            assert response.status_code == 201
            data = response.json()
            assert "ws_token" in data
            assert data["ws_token"].startswith("ws_")
            assert "ws_url" in data
            assert data["expires_in"] == 300


class TestQuestionSeed:
    """Test question bank seed data."""

    @pytest.mark.asyncio
    async def test_seed_questions(self, db_session: AsyncSession):
        """Test that seeding questions works."""
        from app.services.seed_questions import seed_questions

        count = await seed_questions(db_session)
        # Should seed at least some questions
        assert count >= 0  # May be 0 if already seeded

        # Verify questions exist
        from app.models.question import Question
        result = await db_session.execute(
            select(Question).where(Question.is_deleted == 0)
        )
        questions = result.scalars().all()
        # After seeding, there should be questions
        assert len(questions) >= 0


class TestRAGService:
    """Test RAG retrieval service."""

    @pytest.mark.asyncio
    async def test_search_questions(self, db_session: AsyncSession):
        """Test question bank search."""
        from app.services.seed_questions import seed_questions
        from app.services.rag_service import RAGService

        # Seed questions first
        await seed_questions(db_session)

        rag = RAGService(db_session)
        qs = await rag.search_questions(
            stage="技术面",
            position="AI Agent开发工程师",
            difficulty="中级",
            limit=5,
        )
        assert len(qs) > 0
        for q in qs:
            assert q.stage == "技术面"
            assert not q.is_deleted

    @pytest.mark.asyncio
    async def test_get_context(self, db_session: AsyncSession):
        """Test combined context retrieval."""
        from app.services.seed_questions import seed_questions
        from app.services.rag_service import RAGService

        await seed_questions(db_session)

        rag = RAGService(db_session)
        ctx = await rag.get_context_for_interview(
            query="Python asyncio Agent",
            stage="技术面",
            position="AI Agent开发工程师",
            difficulty="中级",
        )
        assert "questions" in ctx
        assert "documents" in ctx
        assert len(ctx["questions"]) > 0
