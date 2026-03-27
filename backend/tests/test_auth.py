import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@test.com", "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "admin@test.com"
    assert data["user"]["role"] == "sales_manager"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin@test.com", "password": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@test.com", "password": "test"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_no_token(client: AsyncClient):
    response = await client.get("/api/v1/dashboard/stats")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_token(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200
