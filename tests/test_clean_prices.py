
import pandas as pd
import pytest

from scripts.clean_prices import clean_price_data


def make_dataframe(prices):
    """Build a small input DataFrame for isolated tests."""
    return pd.DataFrame(
        {
            "product_code": [
                f"{index:04d}"
                for index in range(len(prices))
            ],
            "period": [
                "2026-01-01"
                for _ in prices
            ],
            "average_price_uzs_per_kg": prices,
        }
    )


def test_positive_price_is_preserved():
    df = make_dataframe([1234.5])

    result = clean_price_data(df)

    assert result.loc[0, "source_price_uzs_per_kg"] == 1234.5
    assert result.loc[0, "average_price_uzs_per_kg"] == 1234.5
    assert result.loc[0, "price_status"] == "observed"


def test_zero_is_preserved_but_unavailable_analytically():
    df = make_dataframe([0.0])

    result = clean_price_data(df)

    assert result.loc[0, "source_price_uzs_per_kg"] == 0
    assert pd.isna(result.loc[0, "average_price_uzs_per_kg"])
    assert result.loc[0, "price_status"] == "zero_marked_unavailable"


def test_missing_price_stays_missing():
    df = make_dataframe([None])

    result = clean_price_data(df)

    assert pd.isna(result.loc[0, "source_price_uzs_per_kg"])
    assert pd.isna(result.loc[0, "average_price_uzs_per_kg"])
    assert result.loc[0, "price_status"] == "missing_in_source"


def test_invalid_price_raises_error():
    df = make_dataframe(["not-a-price"])

    with pytest.raises(ValueError, match="invalid price"):
        clean_price_data(df)


def test_negative_price_raises_error():
    df = make_dataframe([-10.0])

    with pytest.raises(ValueError, match="negative prices"):
        clean_price_data(df)
