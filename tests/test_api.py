"""
API unit and integration tests.

Unit-level tests use FastAPI's TestClient with dependency overrides so no
real database is required.  Integration tests (marked ``e2e``) hit a live
database and are skipped when the environment variables are absent.
"""

from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cursor(rows):
    """Return a mock cursor whose fetchone/fetchall returns predictable data."""
    cur = MagicMock()
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = rows[0] if rows else None
    cur.fetchall.return_value = rows
    return cur


def _make_conn(rows):
    conn = MagicMock()
    conn.cursor.return_value = _make_cursor(rows)
    return conn


def _override(rows):
    """Override the database dependency with a predictable fake connection."""

    def _fake():
        return _make_conn(rows)

    app.dependency_overrides[get_connection] = _fake


def _clear():
    app.dependency_overrides.pop(get_connection, None)


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

class TestHealthLive:
    def test_returns_ok(self):
        client = TestClient(app)
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestHealthReady:
    def setup_method(self):
        _override([{"ready": True}])

    def teardown_method(self):
        _clear()

    def test_returns_ok_when_database_ready(self):
        client = TestClient(app)
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["database"] == "ready"

    def test_503_when_database_not_ready(self):
        _override([{"ready": False}])
        client = TestClient(app)
        resp = client.get("/health/ready")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Overview endpoint
# ---------------------------------------------------------------------------

class TestOverview:
    _ROW = {
        "latest_month": None,
        "product_count": 41,
        "available_observations": 2823,
        "unavailable_observations": 6,
        "total_observations": 2829,
        "latest_source_snapshot": "official_prices_20261026T042335Z.json",
        "latest_source_fetched_at_utc": None,
    }

    def setup_method(self):
        _override([self._ROW])

    def teardown_method(self):
        _clear()

    def test_returns_product_count(self):
        client = TestClient(app)
        resp = client.get("/api/v1/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product_count"] == 41

    def test_returns_observation_counts(self):
        client = TestClient(app)
        resp = client.get("/api/v1/overview")
        data = resp.json()
        assert data["available_observations"] == 2823
        assert data["unavailable_observations"] == 6
        assert data["total_observations"] == 2829


# ---------------------------------------------------------------------------
# Products list endpoint
# ---------------------------------------------------------------------------

class TestProductsList:
    _ROW = {
        "product_code": "001",
        "product_name_uz": "Guruch",
        "product_name_ru": "Рис",
        "product_name_en": "Rice",
        "product_name_uz_cyrillic": "Гуруч",
    }
    _COUNT_ROW = {"total": 1}

    def setup_method(self):
        # cursor needs to handle two execute() calls: count then items.
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        # fetchone is called twice; alternate between count and None (items uses fetchall)
        cur.fetchone.side_effect = [self._COUNT_ROW, None]
        cur.fetchall.return_value = [self._ROW]

        conn = MagicMock()
        conn.cursor.return_value = cur

        def _fake():
            return conn

        app.dependency_overrides[get_connection] = _fake

    def teardown_method(self):
        _clear()

    def test_returns_items_list(self):
        client = TestClient(app)
        resp = client.get("/api/v1/products")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["items"], list)
        assert data["items"][0]["product_code"] == "001"

    def test_leading_zero_preserved_in_product_code(self):
        client = TestClient(app)
        resp = client.get("/api/v1/products")
        data = resp.json()
        assert data["items"][0]["product_code"] == "001"

    def test_limit_and_offset_are_echoed(self):
        client = TestClient(app)
        resp = client.get("/api/v1/products?limit=10&offset=5")
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_limit_over_max_is_rejected(self):
        client = TestClient(app)
        resp = client.get("/api/v1/products?limit=999")
        assert resp.status_code == 422

    def test_negative_offset_is_rejected(self):
        client = TestClient(app)
        resp = client.get("/api/v1/products?offset=-1")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Product prices endpoint
# ---------------------------------------------------------------------------

class TestProductPrices:
    _PRODUCT_ROW = {
        "product_code": "001",
        "product_name_uz": None,
        "product_name_ru": None,
        "product_name_en": "Rice",
        "product_name_uz_cyrillic": None,
    }
    _PRICE_ROW = {
        "product_code": "001",
        "product_name_en": "Rice",
        "month_start": "2026-01-01",
        "current_price_uzs_per_kg": Decimal("15000.50"),
        "current_price_status": "observed",
        "previous_month_start": None,
        "previous_price_uzs_per_kg": None,
        "previous_price_status": None,
        "change_uzs_per_kg": None,
        "change_percent": None,
    }
    _COUNT_ROW = {"total": 1}

    def _setup_found(self):
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.side_effect = [self._PRODUCT_ROW, self._COUNT_ROW, None]
        cur.fetchall.return_value = [self._PRICE_ROW]
        conn = MagicMock()
        conn.cursor.return_value = cur

        def _fake():
            return conn

        app.dependency_overrides[get_connection] = _fake

    def _setup_not_found(self):
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = cur

        def _fake():
            return conn

        app.dependency_overrides[get_connection] = _fake

    def teardown_method(self):
        _clear()

    def test_returns_price_history(self):
        self._setup_found()
        client = TestClient(app)
        resp = client.get("/api/v1/products/001/prices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"]["product_code"] == "001"
        assert len(data["items"]) == 1
        assert data["items"][0]["current_price_status"] == "observed"

    def test_missing_price_is_null(self):
        # Build row with null analytical price (zero_marked_unavailable)
        price_row = dict(self._PRICE_ROW)
        price_row["current_price_uzs_per_kg"] = None
        price_row["current_price_status"] = "zero_marked_unavailable"

        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.side_effect = [self._PRODUCT_ROW, self._COUNT_ROW, None]
        cur.fetchall.return_value = [price_row]
        conn = MagicMock()
        conn.cursor.return_value = cur

        def _fake():
            return conn

        app.dependency_overrides[get_connection] = _fake

        client = TestClient(app)
        resp = client.get("/api/v1/products/001/prices")
        assert resp.status_code == 200
        obs = resp.json()["items"][0]
        assert obs["current_price_uzs_per_kg"] is None
        assert obs["current_price_status"] == "zero_marked_unavailable"

    def test_404_for_unknown_product(self):
        self._setup_not_found()
        client = TestClient(app)
        resp = client.get("/api/v1/products/NOTEXIST/prices")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_invalid_from_month_is_rejected(self):
        self._setup_found()
        client = TestClient(app)
        resp = client.get("/api/v1/products/001/prices?from_month=not-a-date")
        assert resp.status_code == 422

    def test_non_first_day_from_month_is_rejected(self):
        self._setup_found()
        client = TestClient(app)
        resp = client.get("/api/v1/products/001/prices?from_month=2026-01-15")
        assert resp.status_code == 422

    def test_inverted_date_range_is_rejected(self):
        self._setup_found()
        client = TestClient(app)
        resp = client.get(
            "/api/v1/products/001/prices?from_month=2026-06-01&to_month=2026-01-01"
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Latest movers endpoint
# ---------------------------------------------------------------------------

class TestLatestMovers:
    _LATEST_ROW = {"latest_month": "2026-09-01"}
    _MOVER_ROW = {
        "product_code": "058",
        "product_name_en": "Tomatoes",
        "month_start": "2026-09-01",
        "comparison_month_start": "2025-09-01",
        "current_price_uzs_per_kg": Decimal("9349.90"),
        "price_12_months_ago_uzs_per_kg": Decimal("6748.80"),
        "change_uzs_per_kg": Decimal("2601.10"),
        "yoy_change_percent": Decimal("38.54"),
        "increase_rank": 1,
        "decrease_rank": None,
    }

    def setup_method(self):
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = self._LATEST_ROW
        cur.fetchall.side_effect = [[self._MOVER_ROW], []]

        conn = MagicMock()
        conn.cursor.return_value = cur

        def _fake():
            return conn

        app.dependency_overrides[get_connection] = _fake

    def teardown_method(self):
        _clear()

    def test_returns_latest_month(self):
        client = TestClient(app)
        resp = client.get("/api/v1/analytics/latest-movers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["latest_month"] == "2026-09-01"

    def test_returns_increases(self):
        client = TestClient(app)
        resp = client.get("/api/v1/analytics/latest-movers")
        data = resp.json()
        assert len(data["increases"]) == 1
        assert data["increases"][0]["product_code"] == "058"
        assert data["increases"][0]["rank"] == 1

    def test_limit_is_validated(self):
        client = TestClient(app)
        resp = client.get("/api/v1/analytics/latest-movers?limit=100")
        assert resp.status_code == 422

    def test_empty_result_when_no_data(self):
        cur = MagicMock()
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)
        cur.fetchone.return_value = {"latest_month": None}
        conn = MagicMock()
        conn.cursor.return_value = cur

        def _fake():
            return conn

        app.dependency_overrides[get_connection] = _fake

        client = TestClient(app)
        resp = client.get("/api/v1/analytics/latest-movers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["increases"] == []
        assert data["decreases"] == []


# ---------------------------------------------------------------------------
# Dashboard route
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_returns_html(self):
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "PricePulse" in resp.text

    def test_contains_dataset_notes(self):
        client = TestClient(app)
        resp = client.get("/")
        assert "zero_marked_unavailable" in resp.text

    def test_static_css_is_served(self):
        client = TestClient(app)
        resp = client.get("/static/app.css")
        assert resp.status_code == 200

    def test_static_js_is_served(self):
        client = TestClient(app)
        resp = client.get("/static/app.js")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# E2E tests: require a live database (marked e2e, skipped without env vars)
# ---------------------------------------------------------------------------

def _db_env_available() -> bool:
    return bool(os.getenv("API_DB_PASSWORD") or os.getenv("DB_PASSWORD"))


def _seed_ci_database_if_empty():
    """If testing against a fresh empty database (such as in CI), seed minimal test data."""
    try:
        import psycopg
        from app.config import get_settings
        settings = get_settings()
        dev_user = os.getenv("DB_USER", "pricepulse_dev")
        dev_password = os.getenv("DB_PASSWORD", settings.db_password)
        with psycopg.connect(
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=dev_user,
            password=dev_password,
            connect_timeout=5,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM analytics.dim_product")
                if cur.fetchone()[0] > 0:
                    return  # already populated, never overwrite!

                cur.execute("""
                    INSERT INTO audit.source_snapshot (
                        snapshot_filename, fetched_at_utc, source_url, raw_sha256, semantic_sha256,
                        semantic_hash_version, product_count, period_count, observation_count, source_metadata
                    ) VALUES (
                        'official_prices_test.json', CURRENT_TIMESTAMP, 'https://api.siat.stat.uz/test',
                        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
                        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
                        2, 2, 3, 6, '[]'::jsonb
                    );

                    INSERT INTO analytics.dim_product (product_code, product_name_uz, product_name_ru, product_name_en, product_name_uz_cyrillic)
                    VALUES 
                        ('001', 'Guruch', 'Рис', 'Rice', 'Гуруч'),
                        ('0050', 'Tarvuz', 'Арбуз', 'Watermelon', 'Тарвуз');

                    INSERT INTO analytics.dim_month (month_key, month_start, calendar_year, quarter_number, month_number)
                    VALUES
                        (202409, '2024-09-01', 2024, 3, 9),
                        (202509, '2025-09-01', 2025, 3, 9),
                        (202609, '2026-09-01', 2026, 3, 9);

                    INSERT INTO analytics.fact_monthly_official_price (
                        product_key, month_key, source_price_uzs_per_kg, average_price_uzs_per_kg, price_status, source_fetched_at_utc, source_snapshot
                    )
                    SELECT p.product_key, m.month_key,
                        CASE 
                            WHEN p.product_code = '001' AND m.month_key = 202409 THEN 10000.00
                            WHEN p.product_code = '001' AND m.month_key = 202509 THEN 12000.00
                            WHEN p.product_code = '001' AND m.month_key = 202609 THEN 15000.00
                            WHEN p.product_code = '0050' AND m.month_key = 202409 THEN 2000.00
                            WHEN p.product_code = '0050' AND m.month_key = 202509 THEN 2500.00
                            WHEN p.product_code = '0050' AND m.month_key = 202609 THEN 0.00
                        END,
                        CASE 
                            WHEN p.product_code = '001' AND m.month_key = 202409 THEN 10000.00
                            WHEN p.product_code = '001' AND m.month_key = 202509 THEN 12000.00
                            WHEN p.product_code = '001' AND m.month_key = 202609 THEN 15000.00
                            WHEN p.product_code = '0050' AND m.month_key = 202409 THEN 2000.00
                            WHEN p.product_code = '0050' AND m.month_key = 202509 THEN 2500.00
                            WHEN p.product_code = '0050' AND m.month_key = 202609 THEN NULL
                        END,
                        CASE 
                            WHEN p.product_code = '0050' AND m.month_key = 202609 THEN 'zero_marked_unavailable'
                            ELSE 'observed'
                        END,
                        CURRENT_TIMESTAMP, 'official_prices_test.json'
                    FROM analytics.dim_product p
                    CROSS JOIN analytics.dim_month m;
                """)
            conn.commit()
    except Exception as exc:
        import logging
        logging.getLogger("test").warning("Could not auto-seed test DB: %s", exc)


@pytest.mark.e2e
class TestE2EApi:
    """Smoke tests against the actual PostgreSQL database.

    Run with:
        pytest -m e2e tests/test_api.py
    """

    @pytest.fixture(autouse=True)
    def skip_without_db(self):
        if not _db_env_available():
            pytest.skip("No database credentials in environment")
        _seed_ci_database_if_empty()

    def test_overview_returns_real_data(self):
        client = TestClient(app)
        resp = client.get("/api/v1/overview")
        assert resp.status_code == 200
        data = resp.json()
        # Actual counts from the database
        assert data["product_count"] > 0
        assert data["total_observations"] > 0

    def test_products_returns_all_products(self):
        client = TestClient(app)
        resp = client.get("/api/v1/products?limit=200")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        # Leading-zero codes must survive round-trip
        codes = {p["product_code"] for p in data["items"]}
        assert "001" in codes

    def test_rice_price_history_is_available(self):
        client = TestClient(app)
        resp = client.get("/api/v1/products/001/prices?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"]["product_name_en"] == "Rice"
        assert data["total"] > 0
        # No fabricated zeros: all observed prices must be positive
        for item in data["items"]:
            if item["current_price_status"] == "observed":
                assert float(item["current_price_uzs_per_kg"]) > 0

    def test_zero_marked_observations_have_null_analytical_price(self):
        """Source zeros must propagate as NULL analytical price, not zero."""
        client = TestClient(app)
        # Fetch all products' prices, looking for zero_marked_unavailable rows
        resp = client.get("/api/v1/products?limit=200")
        data = resp.json()
        found_unavailable = False
        for product in data["items"]:
            presp = client.get(
                f"/api/v1/products/{product['product_code']}/prices?limit=200"
            )
            assert presp.status_code == 200
            for obs in presp.json()["items"]:
                if obs["current_price_status"] == "zero_marked_unavailable":
                    assert obs["current_price_uzs_per_kg"] is None, (
                        f"Product {product['product_code']}: zero_marked_unavailable "
                        "must have NULL analytical price"
                    )
                    found_unavailable = True
        # We know there are 6 such observations in the dataset
        assert found_unavailable, "Expected at least one zero_marked_unavailable observation"

    def test_unknown_product_returns_404(self):
        client = TestClient(app)
        resp = client.get("/api/v1/products/NOTEXIST_CODE_XYZ/prices")
        assert resp.status_code == 404

    def test_latest_movers_returns_rankings(self):
        client = TestClient(app)
        resp = client.get("/api/v1/analytics/latest-movers?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["latest_month"] is not None
        assert len(data["increases"]) > 0 or len(data["decreases"]) > 0
        # Ranks must start at 1 and be positive integers
        for mover in data["increases"] + data["decreases"]:
            assert mover["rank"] >= 1

    def test_health_ready_with_real_db(self):
        client = TestClient(app)
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        assert resp.json()["database"] == "ready"

