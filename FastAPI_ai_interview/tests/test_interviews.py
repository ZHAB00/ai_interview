"""Tests for interview endpoints."""

import io
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient


MOCK_PARSED_DATA = {
    "name": "李四",
    "phone": "13900139001",
    "email": "lisi@example.com",
    "education": [],
    "skills": ["Python", "FastAPI"],
    "work_experience": [],
    "project_experience": [],
    "position_match_score": 80,
    "match_feedback": "技能匹配",
}


@pytest_asyncio.fixture
async def auth_and_resume(client: AsyncClient) -> tuple[dict, int]:
    """Register, login, upload resume, return (headers, resume_id)."""
    # Register & login
    await client.post("/api/auth/register", json={
        "phone": "13900139001",
        "username": "interviewtest",
        "password": "123456",
    })
    login_resp = await client.post("/api/auth/login", json={
        "phone": "13900139001",
        "password": "123456",
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload a minimal resume PDF (mock LLM to avoid real API calls)
    pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
    files = {"file": ("resume.pdf", io.BytesIO(pdf_content), "application/pdf")}
    with patch("app.services.resume_parser.ResumeAgent.analyze", return_value=MOCK_PARSED_DATA):
        resume_resp = await client.post(
            "/api/resumes/upload",
            data={"position": "AI Agent开发工程师", "difficulty": "中级"},
            files=files,
            headers=headers,
        )
    resume_id = resume_resp.json().get("resume_id", 1)
    return headers, resume_id


@pytest.mark.asyncio
async def test_create_interview_success(client: AsyncClient, auth_and_resume: tuple):
    """正向流程：创建面试成功。"""
    headers, resume_id = auth_and_resume

    response = await client.post(
        "/api/interviews",
        json={
            "resume_id": resume_id,
            "position": "AI Agent开发工程师",
            "difficulty": "中级",
            "mode": "full",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert "interview_id" in data
    assert "ws_token" in data
    assert "ws_url" in data


@pytest.mark.asyncio
async def test_create_interview_stage_mode(client: AsyncClient, auth_and_resume: tuple):
    """正向流程：创建阶段练习模式面试。"""
    headers, resume_id = auth_and_resume

    response = await client.post(
        "/api/interviews",
        json={
            "resume_id": resume_id,
            "position": "AI Agent开发工程师",
            "difficulty": "中级",
            "mode": "stage",
            "selected_stages": ["技术面"],
        },
        headers=headers,
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_interview_stage_no_stages(client: AsyncClient, auth_and_resume: tuple):
    """验证失败：阶段练习模式未选择阶段。"""
    headers, resume_id = auth_and_resume

    response = await client.post(
        "/api/interviews",
        json={
            "resume_id": resume_id,
            "position": "AI Agent开发工程师",
            "difficulty": "中级",
            "mode": "stage",
        },
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_history(client: AsyncClient, auth_and_resume: tuple):
    """正向流程：获取面试历史。"""
    headers, resume_id = auth_and_resume

    # Create an interview first
    await client.post(
        "/api/interviews",
        json={
            "resume_id": resume_id,
            "position": "AI Agent开发工程师",
            "difficulty": "中级",
            "mode": "full",
        },
        headers=headers,
    )

    response = await client.get("/api/interviews/history", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1
