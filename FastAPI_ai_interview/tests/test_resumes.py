"""Tests for resume endpoints."""

import io
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient


MOCK_PARSED_DATA = {
    "name": "张三",
    "phone": "13800138000",
    "email": "zhangsan@example.com",
    "education": [],
    "skills": ["Python", "FastAPI"],
    "work_experience": [],
    "project_experience": [],
    "position_match_score": 85,
    "match_feedback": "技能匹配度较高",
}


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Register and login, return Authorization headers."""
    await client.post("/api/auth/register", json={
        "phone": "13900139000",
        "username": "resumetest",
        "password": "123456",
    })
    resp = await client.post("/api/auth/login", json={
        "phone": "13900139000",
        "password": "123456",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_upload_resume_no_auth(client: AsyncClient):
    """验证失败：未登录上传简历。"""
    response = await client.post("/api/resumes/upload")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_resume_invalid_format(client: AsyncClient, auth_headers: dict):
    """验证失败：不支持的文件格式。"""
    files = {"file": ("test.txt", io.BytesIO(b"some text"), "text/plain")}
    response = await client.post(
        "/api/resumes/upload",
        data={"position": "AI Agent开发工程师"},
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@patch("app.services.resume_parser.ResumeAgent.analyze", return_value=MOCK_PARSED_DATA)
async def test_upload_resume_pdf(mock_analyze, client: AsyncClient, auth_headers: dict):
    """正向流程：上传PDF简历（mock LLM 调用）。"""
    pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
    files = {"file": ("resume.pdf", io.BytesIO(pdf_content), "application/pdf")}
    response = await client.post(
        "/api/resumes/upload",
        data={"position": "AI Agent开发工程师", "difficulty": "中级"},
        files=files,
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["resume_id"] is not None
    assert data["parsed_data"]["name"] == "张三"
    assert data["position_match_score"] == 85


@pytest.mark.asyncio
async def test_get_resume_not_found(client: AsyncClient, auth_headers: dict):
    """验证失败：获取不存在的简历。"""
    response = await client.get("/api/resumes/99999", headers=auth_headers)
    assert response.status_code == 404
