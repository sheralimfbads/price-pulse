
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "official_prices_long.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "official_prices_analytics.csv"
)

REQUIRED_COLUMNS = {
    "product_code",
    "period",
    "average_price_uzs_per_kg",
}


def clean_price_data(df: pd.DataFrame) -> pd.DataFrame:
    """Create an analytical dataset without changing source values."""
    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    result = df.copy()

    raw_prices = result["average_price_uzs_per_kg"]
    numeric_prices = pd.to_numeric(
        raw_prices,
        errors="coerce",
    )

    # Distinguish genuinely missing values from malformed values.
    nonempty = (
        raw_prices.notna()
        & raw_prices.astype("string").str.strip().ne("").fillna(False)
    )

    invalid = nonempty & numeric_prices.isna()

    if invalid.any():
        raise ValueError(
            f"Found {int(invalid.sum())} invalid price values"
        )

    # Prices must be finite and non-negative.
    infinite_prices = numeric_prices.isin(
        [float("inf"), float("-inf")]
    )

    if infinite_prices.any():
        raise ValueError("Infinite prices are not allowed")

    negative_prices = numeric_prices.lt(0).fillna(False)

    if negative_prices.any():
        raise ValueError(
            f"Found {int(negative_prices.sum())} negative prices"
        )

    # Preserve the value as received by the source.
    result = result.rename(
        columns={
            "average_price_uzs_per_kg": "source_price_uzs_per_kg"
        }
    )

    result["source_price_uzs_per_kg"] = pd.array(
        numeric_prices,
        dtype="Float64",
    )

    # Apply our documented analytical rule.
    clean_prices = numeric_prices.mask(
        numeric_prices.eq(0),
        pd.NA,
    )

    result["average_price_uzs_per_kg"] = pd.array(
        clean_prices,
        dtype="Float64",
    )

    # Make the cleaning decision visible for every observation.
    status = pd.Series(
        "observed",
        index=result.index,
        dtype="string",
    )

    status.loc[numeric_prices.isna()] = "missing_in_source"
    status.loc[numeric_prices.eq(0)] = "zero_marked_unavailable"

    result["price_status"] = status

    return result


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input dataset not found: {INPUT_FILE}"
        )

    df = pd.read_csv(
        INPUT_FILE,
        dtype={
            "product_code": "string",
            "period": "string",
        },
    )

    cleaned = clean_price_data(df)

    # Write to a temporary file before replacing the output.
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    temporary_file = OUTPUT_FILE.with_suffix(".csv.tmp")

    try:
        cleaned.to_csv(
            temporary_file,
            index=False,
            na_rep="",
        )

        temporary_file.replace(OUTPUT_FILE)

    except Exception:
        temporary_file.unlink(missing_ok=True)
        raise

    print("=== CLEANING SUMMARY ===")
    print(f"Input rows: {len(df):,}")
    print(f"Output rows: {len(cleaned):,}")

    print("\nPrice status counts:")
    print(cleaned["price_status"].value_counts().to_string())

    print(
        "\nSource zero values preserved:",
        int(cleaned["source_price_uzs_per_kg"].eq(0).sum()),
    )

    print(
        "Analytical prices missing:",
        int(cleaned["average_price_uzs_per_kg"].isna().sum()),
    )

    print(f"\nOutput file: {OUTPUT_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
