from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.field_permission import FieldPermission
from app.services.field_permission_service import FieldPermissionService


@pytest.fixture(autouse=True)
def enable_feature_flag(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_FIELD_PERMISSIONS", True)


class TestFieldPermissionService:
    """Unit tests for FieldPermissionService."""

    @pytest.mark.asyncio
    async def test_set_permission_creates_new(self, db: AsyncSession):
        service = FieldPermissionService(db)
        perm = await service.set_permission(
            role="sales_rep",
            entity_type="customer",
            field_name="email",
            access_level="masked",
        )

        assert perm.id is not None
        assert perm.role == "sales_rep"
        assert perm.entity_type == "customer"
        assert perm.field_name == "email"
        assert perm.access_level == "masked"

    @pytest.mark.asyncio
    async def test_set_permission_updates_existing(self, db: AsyncSession):
        service = FieldPermissionService(db)
        perm1 = await service.set_permission(
            role="sales_rep",
            entity_type="customer",
            field_name="phone",
            access_level="read",
        )
        perm2 = await service.set_permission(
            role="sales_rep",
            entity_type="customer",
            field_name="phone",
            access_level="hidden",
        )

        assert perm1.id == perm2.id
        assert perm2.access_level == "hidden"

    @pytest.mark.asyncio
    async def test_set_permission_invalid_access_level(self, db: AsyncSession):
        service = FieldPermissionService(db)
        with pytest.raises(ValueError, match="Gecersiz erisim seviyesi"):
            await service.set_permission(
                role="sales_rep",
                entity_type="customer",
                field_name="email",
                access_level="invalid",
            )

    @pytest.mark.asyncio
    async def test_set_permission_invalid_role(self, db: AsyncSession):
        service = FieldPermissionService(db)
        with pytest.raises(ValueError, match="Gecersiz rol"):
            await service.set_permission(
                role="invalid_role",
                entity_type="customer",
                field_name="email",
                access_level="read",
            )

    @pytest.mark.asyncio
    async def test_hidden_field_removed_from_response(self, db: AsyncSession):
        service = FieldPermissionService(db)
        await service.set_permission(
            role="sales_rep",
            entity_type="customer",
            field_name="tax_id",
            access_level="hidden",
        )

        data = {"name": "Acme Corp", "tax_id": "1234567890", "email": "info@acme.com"}
        filtered = await service.apply_to_response(data, "sales_rep", "customer")

        assert "tax_id" not in filtered
        assert filtered["name"] == "Acme Corp"
        assert filtered["email"] == "info@acme.com"

    @pytest.mark.asyncio
    async def test_masked_field_shows_masked_value(self, db: AsyncSession):
        service = FieldPermissionService(db)
        await service.set_permission(
            role="sales_rep",
            entity_type="customer",
            field_name="email",
            access_level="masked",
        )

        data = {"name": "Acme Corp", "email": "onur@domain.com"}
        filtered = await service.apply_to_response(data, "sales_rep", "customer")

        assert filtered["name"] == "Acme Corp"
        assert "@domain.com" in filtered["email"]
        assert filtered["email"].startswith("o***")

    @pytest.mark.asyncio
    async def test_get_permissions_returns_dict(self, db: AsyncSession):
        service = FieldPermissionService(db)
        await service.set_permission("sales_rep", "customer", "email", "masked")
        await service.set_permission("sales_rep", "customer", "tax_id", "hidden")

        perms = await service.get_permissions("sales_rep", "customer")

        assert perms == {"email": "masked", "tax_id": "hidden"}

    @pytest.mark.asyncio
    async def test_list_permissions_with_filters(self, db: AsyncSession):
        service = FieldPermissionService(db)
        await service.set_permission("sales_rep", "customer", "email", "masked")
        await service.set_permission("sales_rep", "quote", "amount", "hidden")
        await service.set_permission("operations", "customer", "phone", "read")

        all_perms = await service.list_permissions()
        assert len(all_perms) == 3

        rep_perms = await service.list_permissions(role="sales_rep")
        assert len(rep_perms) == 2

        customer_perms = await service.list_permissions(entity_type="customer")
        assert len(customer_perms) == 2

    @pytest.mark.asyncio
    async def test_delete_permission(self, db: AsyncSession):
        service = FieldPermissionService(db)
        perm = await service.set_permission("sales_rep", "customer", "email", "masked")

        deleted = await service.delete_permission(perm.id)
        assert deleted is True

        # Verify it's gone
        perms = await service.list_permissions()
        assert len(perms) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_permission(self, db: AsyncSession):
        service = FieldPermissionService(db)
        deleted = await service.delete_permission(99999)
        assert deleted is False

    def test_mask_email(self):
        result = FieldPermissionService.mask_value("onur@domain.com", "email")
        assert result == "o***@domain.com"

    def test_mask_phone(self):
        result = FieldPermissionService.mask_value("+90 555 123 4567", "phone")
        assert result.endswith("67")
        assert "***" in result

    def test_mask_tax_id(self):
        result = FieldPermissionService.mask_value("1234567890", "tax_id")
        assert result == "***890"


class TestFieldPermissionsAPI:
    """Integration tests for field permissions endpoints."""

    @pytest.mark.asyncio
    async def test_manager_can_create_permission(
        self, client: AsyncClient, auth_headers: dict,
    ):
        response = await client.post(
            "/api/v1/field-permissions/",
            json={
                "role": "sales_rep",
                "entity_type": "customer",
                "field_name": "email",
                "access_level": "masked",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "sales_rep"
        assert data["access_level"] == "masked"

    @pytest.mark.asyncio
    async def test_manager_can_list_permissions(
        self, client: AsyncClient, auth_headers: dict,
    ):
        # Create a permission first
        await client.post(
            "/api/v1/field-permissions/",
            json={
                "role": "sales_rep",
                "entity_type": "customer",
                "field_name": "phone",
                "access_level": "hidden",
            },
            headers=auth_headers,
        )

        response = await client.get(
            "/api/v1/field-permissions/",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_manager_can_delete_permission(
        self, client: AsyncClient, auth_headers: dict,
    ):
        # Create
        create_resp = await client.post(
            "/api/v1/field-permissions/",
            json={
                "role": "operations",
                "entity_type": "lead",
                "field_name": "email",
                "access_level": "masked",
            },
            headers=auth_headers,
        )
        perm_id = create_resp.json()["id"]

        # Delete
        delete_resp = await client.delete(
            f"/api/v1/field-permissions/{perm_id}",
            headers=auth_headers,
        )
        assert delete_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_feature_flag_disabled_returns_404(
        self, client: AsyncClient, auth_headers: dict, monkeypatch,
    ):
        monkeypatch.setattr(settings, "FEATURE_FIELD_PERMISSIONS", False)

        response = await client.get(
            "/api/v1/field-permissions/",
            headers=auth_headers,
        )
        assert response.status_code == 404
