"""Integration tests for dimension list sorting (sort_by / sort_order).

Runs against a real PostgreSQL database. Each test scopes its assertions
to a unique TEST- prefix via the ``search`` filter so pre-existing seeded
rows do not interfere.

Requires PostgreSQL to be running: docker-compose up -d
"""

import pytest
from httpx import AsyncClient

from app.features.data_platform.models import Product, Store


def _prefix(code_or_sku: str) -> str:
    """Recover the shared TEST- prefix from a ``{prefix}-A`` code/sku."""
    return code_or_sku.rsplit("-", 1)[0]


@pytest.mark.integration
@pytest.mark.asyncio
class TestStoreSort:
    """Sorting on GET /dimensions/stores."""

    async def test_sort_by_name_asc(
        self, client: AsyncClient, sample_stores_multi: list[Store]
    ) -> None:
        """sort_by=name&sort_order=asc orders stores by name ascending."""
        prefix = _prefix(sample_stores_multi[0].code)
        response = await client.get(
            "/dimensions/stores",
            params={"search": prefix, "sort_by": "name", "sort_order": "asc"},
        )
        assert response.status_code == 200
        stores = response.json()["stores"]
        assert len(stores) == 3
        assert [s["name"] for s in stores] == [
            "Alpha Store",
            "Mike Store",
            "Zulu Store",
        ]

    async def test_sort_by_name_desc(
        self, client: AsyncClient, sample_stores_multi: list[Store]
    ) -> None:
        """sort_by=name&sort_order=desc orders stores by name descending."""
        prefix = _prefix(sample_stores_multi[0].code)
        response = await client.get(
            "/dimensions/stores",
            params={"search": prefix, "sort_by": "name", "sort_order": "desc"},
        )
        assert response.status_code == 200
        stores = response.json()["stores"]
        assert [s["name"] for s in stores] == [
            "Zulu Store",
            "Mike Store",
            "Alpha Store",
        ]

    async def test_unknown_sort_by_falls_back_to_default(
        self, client: AsyncClient, sample_stores_multi: list[Store]
    ) -> None:
        """An unknown sort_by falls back to the default code order (no error)."""
        prefix = _prefix(sample_stores_multi[0].code)
        response = await client.get(
            "/dimensions/stores",
            params={"search": prefix, "sort_by": "not_a_real_column"},
        )
        assert response.status_code == 200
        codes = [s["code"] for s in response.json()["stores"]]
        assert codes == sorted(codes)

    async def test_omitted_sort_is_default_code_order(
        self, client: AsyncClient, sample_stores_multi: list[Store]
    ) -> None:
        """Omitting sort params preserves the prior default (code ascending)."""
        prefix = _prefix(sample_stores_multi[0].code)
        response = await client.get(
            "/dimensions/stores",
            params={"search": prefix},
        )
        assert response.status_code == 200
        codes = [s["code"] for s in response.json()["stores"]]
        assert codes == sorted(codes)


@pytest.mark.integration
@pytest.mark.asyncio
class TestProductSort:
    """Sorting on GET /dimensions/products."""

    async def test_sort_by_name_asc(
        self, client: AsyncClient, sample_products_multi: list[Product]
    ) -> None:
        """sort_by=name&sort_order=asc orders products by name ascending."""
        prefix = _prefix(sample_products_multi[0].sku)
        response = await client.get(
            "/dimensions/products",
            params={"search": prefix, "sort_by": "name", "sort_order": "asc"},
        )
        assert response.status_code == 200
        products = response.json()["products"]
        assert len(products) == 3
        assert [p["name"] for p in products] == [
            "Alpha Widget",
            "Mike Widget",
            "Zulu Widget",
        ]

    async def test_sort_by_name_desc(
        self, client: AsyncClient, sample_products_multi: list[Product]
    ) -> None:
        """sort_by=name&sort_order=desc orders products by name descending."""
        prefix = _prefix(sample_products_multi[0].sku)
        response = await client.get(
            "/dimensions/products",
            params={"search": prefix, "sort_by": "name", "sort_order": "desc"},
        )
        assert response.status_code == 200
        products = response.json()["products"]
        assert [p["name"] for p in products] == [
            "Zulu Widget",
            "Mike Widget",
            "Alpha Widget",
        ]

    async def test_sort_by_base_price_asc(
        self, client: AsyncClient, sample_products_multi: list[Product]
    ) -> None:
        """sort_by=base_price orders by the numeric price column."""
        prefix = _prefix(sample_products_multi[0].sku)
        response = await client.get(
            "/dimensions/products",
            params={"search": prefix, "sort_by": "base_price", "sort_order": "asc"},
        )
        assert response.status_code == 200
        products = response.json()["products"]
        assert [p["name"] for p in products] == [
            "Alpha Widget",
            "Mike Widget",
            "Zulu Widget",
        ]

    async def test_unknown_sort_by_falls_back_to_default(
        self, client: AsyncClient, sample_products_multi: list[Product]
    ) -> None:
        """An unknown sort_by falls back to the default sku order (no error)."""
        prefix = _prefix(sample_products_multi[0].sku)
        response = await client.get(
            "/dimensions/products",
            params={"search": prefix, "sort_by": "not_a_real_column"},
        )
        assert response.status_code == 200
        skus = [p["sku"] for p in response.json()["products"]]
        assert skus == sorted(skus)
