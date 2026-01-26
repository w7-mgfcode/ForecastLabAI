"""Tests for data platform ORM models."""

from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    PriceHistory,
    Product,
    Promotion,
    SalesDaily,
    Store,
)


class TestStoreModel:
    """Tests for Store model."""

    def test_store_tablename(self):
        """Store model should have correct table name."""
        assert Store.__tablename__ == "store"

    def test_store_has_required_columns(self):
        """Store model should have all required columns."""
        columns = {c.name for c in Store.__table__.columns}
        required = {
            "id",
            "code",
            "name",
            "region",
            "city",
            "store_type",
            "created_at",
            "updated_at",
        }
        assert required.issubset(columns)

    def test_store_code_is_unique(self):
        """Store code column should be unique."""
        code_col = Store.__table__.columns["code"]
        assert code_col.unique is True

    def test_store_has_relationships(self):
        """Store model should have relationships to fact tables."""
        relationships = {rel.key for rel in Store.__mapper__.relationships}
        expected = {"sales", "price_history", "promotions", "inventory_snapshots"}
        assert expected == relationships


class TestProductModel:
    """Tests for Product model."""

    def test_product_tablename(self):
        """Product model should have correct table name."""
        assert Product.__tablename__ == "product"

    def test_product_has_required_columns(self):
        """Product model should have all required columns."""
        columns = {c.name for c in Product.__table__.columns}
        required = {
            "id",
            "sku",
            "name",
            "category",
            "brand",
            "base_price",
            "base_cost",
            "created_at",
            "updated_at",
        }
        assert required.issubset(columns)

    def test_product_sku_is_unique(self):
        """Product SKU column should be unique."""
        sku_col = Product.__table__.columns["sku"]
        assert sku_col.unique is True

    def test_product_price_is_numeric(self):
        """Product base_price should be Numeric type."""
        price_col = Product.__table__.columns["base_price"]
        assert "NUMERIC" in str(price_col.type).upper()

    def test_product_has_relationships(self):
        """Product model should have relationships to fact tables."""
        relationships = {rel.key for rel in Product.__mapper__.relationships}
        expected = {"sales", "price_history", "promotions", "inventory_snapshots"}
        assert expected == relationships


class TestCalendarModel:
    """Tests for Calendar model."""

    def test_calendar_tablename(self):
        """Calendar model should have correct table name."""
        assert Calendar.__tablename__ == "calendar"

    def test_calendar_date_is_primary_key(self):
        """Calendar date should be primary key."""
        date_col = Calendar.__table__.columns["date"]
        assert date_col.primary_key is True

    def test_calendar_has_required_columns(self):
        """Calendar model should have all required columns."""
        columns = {c.name for c in Calendar.__table__.columns}
        required = {
            "date",
            "day_of_week",
            "month",
            "quarter",
            "year",
            "is_holiday",
            "holiday_name",
            "created_at",
            "updated_at",
        }
        assert required.issubset(columns)

    def test_calendar_has_check_constraints(self):
        """Calendar should have check constraints for date fields."""
        constraints = [c.name for c in Calendar.__table__.constraints if hasattr(c, "name")]
        assert "ck_calendar_day_of_week" in constraints
        assert "ck_calendar_month" in constraints
        assert "ck_calendar_quarter" in constraints


class TestSalesDailyModel:
    """Tests for SalesDaily model."""

    def test_sales_daily_tablename(self):
        """SalesDaily model should have correct table name."""
        assert SalesDaily.__tablename__ == "sales_daily"

    def test_sales_daily_has_required_columns(self):
        """SalesDaily model should have all required columns."""
        columns = {c.name for c in SalesDaily.__table__.columns}
        required = {
            "id",
            "date",
            "store_id",
            "product_id",
            "quantity",
            "unit_price",
            "total_amount",
            "created_at",
            "updated_at",
        }
        assert required.issubset(columns)

    def test_sales_daily_has_grain_constraint(self):
        """SalesDaily should have unique constraint on grain."""
        constraints = [c.name for c in SalesDaily.__table__.constraints]
        assert "uq_sales_daily_grain" in constraints

    def test_sales_daily_has_foreign_keys(self):
        """SalesDaily should have foreign keys to dimensions."""
        fk_columns = {fk.column.table.name for fk in SalesDaily.__table__.foreign_keys}
        assert fk_columns == {"calendar", "store", "product"}

    def test_sales_daily_has_check_constraints(self):
        """SalesDaily should have check constraints for data quality."""
        constraints = [c.name for c in SalesDaily.__table__.constraints if hasattr(c, "name")]
        assert "ck_sales_daily_quantity_positive" in constraints
        assert "ck_sales_daily_price_positive" in constraints
        assert "ck_sales_daily_amount_positive" in constraints

    def test_sales_daily_has_relationships(self):
        """SalesDaily should have relationships to dimension tables."""
        relationships = {rel.key for rel in SalesDaily.__mapper__.relationships}
        expected = {"store", "product", "calendar"}
        assert expected == relationships


class TestPriceHistoryModel:
    """Tests for PriceHistory model."""

    def test_price_history_tablename(self):
        """PriceHistory model should have correct table name."""
        assert PriceHistory.__tablename__ == "price_history"

    def test_price_history_has_validity_dates(self):
        """PriceHistory should have valid_from and valid_to columns."""
        columns = {c.name for c in PriceHistory.__table__.columns}
        assert "valid_from" in columns
        assert "valid_to" in columns

    def test_price_history_has_check_constraints(self):
        """PriceHistory should have check constraints."""
        constraints = [c.name for c in PriceHistory.__table__.constraints if hasattr(c, "name")]
        assert "ck_price_history_price_positive" in constraints
        assert "ck_price_history_valid_dates" in constraints

    def test_price_history_store_id_is_nullable(self):
        """PriceHistory store_id should be nullable for chain-wide prices."""
        store_id_col = PriceHistory.__table__.columns["store_id"]
        assert store_id_col.nullable is True


class TestPromotionModel:
    """Tests for Promotion model."""

    def test_promotion_tablename(self):
        """Promotion model should have correct table name."""
        assert Promotion.__tablename__ == "promotion"

    def test_promotion_has_discount_fields(self):
        """Promotion should have discount_pct and discount_amount."""
        columns = {c.name for c in Promotion.__table__.columns}
        assert "discount_pct" in columns
        assert "discount_amount" in columns

    def test_promotion_has_date_fields(self):
        """Promotion should have start_date and end_date."""
        columns = {c.name for c in Promotion.__table__.columns}
        assert "start_date" in columns
        assert "end_date" in columns

    def test_promotion_has_check_constraints(self):
        """Promotion should have check constraints."""
        constraints = [c.name for c in Promotion.__table__.constraints if hasattr(c, "name")]
        assert "ck_promotion_valid_dates" in constraints
        assert "ck_promotion_discount_pct_range" in constraints
        assert "ck_promotion_discount_amount_positive" in constraints


class TestInventorySnapshotDailyModel:
    """Tests for InventorySnapshotDaily model."""

    def test_inventory_tablename(self):
        """InventorySnapshotDaily model should have correct table name."""
        assert InventorySnapshotDaily.__tablename__ == "inventory_snapshot_daily"

    def test_inventory_has_required_columns(self):
        """InventorySnapshotDaily model should have all required columns."""
        columns = {c.name for c in InventorySnapshotDaily.__table__.columns}
        required = {
            "id",
            "date",
            "store_id",
            "product_id",
            "on_hand_qty",
            "on_order_qty",
            "is_stockout",
            "created_at",
            "updated_at",
        }
        assert required.issubset(columns)

    def test_inventory_has_grain_constraint(self):
        """InventorySnapshotDaily should have unique constraint on grain."""
        constraints = [c.name for c in InventorySnapshotDaily.__table__.constraints]
        assert "uq_inventory_snapshot_daily_grain" in constraints

    def test_inventory_has_check_constraints(self):
        """InventorySnapshotDaily should have check constraints."""
        constraints = [
            c.name for c in InventorySnapshotDaily.__table__.constraints if hasattr(c, "name")
        ]
        assert "ck_inventory_on_hand_positive" in constraints
        assert "ck_inventory_on_order_positive" in constraints

    def test_inventory_has_relationships(self):
        """InventorySnapshotDaily should have relationships to dimension tables."""
        relationships = {rel.key for rel in InventorySnapshotDaily.__mapper__.relationships}
        expected = {"store", "product", "calendar"}
        assert expected == relationships
