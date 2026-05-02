"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """正向流程：注册成功。"""
    response = await client.post("/api/auth/register", json={
        "phone": "13800138000",
        "username": "testuser",
        "password": "123456",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["phone"] == "13800138000"
    assert data["username"] == "testuser"
    assert data["role"] == "candidate"
    assert "user_id" in data


@pytest.mark.asyncio
async def test_register_duplicate_phone(client: AsyncClient):
    """验证失败：重复手机号注册。"""
    await client.post("/api/auth/register", json={
        "phone": "13800138000",
        "username": "user1",
        "password": "123456",
    })
    response = await client.post("/api/auth/register", json={
        "phone": "13800138000",
        "username": "user2",
        "password": "123456",
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_phone(client: AsyncClient):
    """验证失败：手机号格式错误。"""
    response = await client.post("/api/auth/register", json={
        "phone": "12345",
        "username": "testuser",
        "password": "123456",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """正向流程：登录成功。"""
    # Register first
    await client.post("/api/auth/register", json={
        "phone": "13800138000",
        "username": "testuser",
        "password": "123456",
    })
    # Login
    response = await client.post("/api/auth/login", json={
        "phone": "13800138000",
        "password": "123456",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """验证失败：密码错误。"""
    await client.post("/api/auth/register", json={
        "phone": "13800138000",
        "username": "testuser",
        "password": "123456",
    })
    response = await client.post("/api/auth/login", json={
        "phone": "13800138000",
        "password": "wrongpass",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    """正向流程：刷新令牌。"""
    # Register and login
    await client.post("/api/auth/register", json={
        "phone": "13800138000",
        "username": "testuser",
        "password": "123456",
    })
    login_resp = await client.post("/api/auth/login", json={
        "phone": "13800138000",
        "password": "123456",
    })
    refresh_token = login_resp.json()["refresh_token"]

    # Refresh
    response = await client.post("/api/auth/refresh", json={
        "refresh_token": refresh_token,
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    """验证失败：无效刷新令牌。"""
    response = await client.post("/api/auth/refresh", json={
        "refresh_token": "invalid_token_here",
    })
    assert response.status_code == 401
