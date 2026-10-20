
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "official_prices_long.csv"
)

REQUIRED_COLUMNS = {
    "product_code",
    "product_name_uz",
    "product_name_en",
    "period",
    "average_price_uzs_per_kg",
    "source_fetched_at_utc",
    "source_snapshot",
}


def main() -> None:
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Processed dataset not found: {DATA_FILE}"
        )

    # Preserve product identifiers such as "001".
    df = pd.read_csv(
        DATA_FILE,
        dtype={
            "product_code": "string",
            "period": "string",
            "source_fetched_at_utc": "string",
            "source_snapshot": "string",
        },
    )

    print("=== DATASET OVERVIEW ===")
    print(f"File: {DATA_FILE.name}")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")
    print(f"Memory usage: {df.memory_usage(deep=True).sum():,} bytes")

    print("\n=== COLUMN TYPES ===")
    print(df.dtypes.to_string())

    # Check whether our expected schema is present.
    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        print("\nFAIL: Required columns are missing:")
        for column in sorted(missing_columns):
            print(f"  - {column}")

        sys.exit(1)

    errors = []
    warnings = []

    # Parse dates without silently accepting invalid ones.
    raw_period = df["period"]
    parsed_period = pd.to_datetime(
        raw_period,
        format="%Y-%m-%d",
        errors="coerce",
    )

    invalid_dates = int(
        (raw_period.notna() & parsed_period.isna()).sum()
    )

    missing_dates = int(raw_period.isna().sum())

    print("\n=== DATE VALIDATION ===")
    print(f"Invalid dates: {invalid_dates}")
    print(f"Missing dates: {missing_dates}")

    if invalid_dates or missing_dates:
        errors.append("Invalid or missing observation dates")

    valid_periods = pd.DatetimeIndex(
        parsed_period.dropna().unique()
    ).sort_values()

    if len(valid_periods):
        print(f"Earliest month: {valid_periods.min():%Y-%m}")
        print(f"Latest month: {valid_periods.max():%Y-%m}")

        # Check whether any months are absent from the timeline.
        expected_periods = pd.date_range(
            start=valid_periods.min(),
            end=valid_periods.max(),
            freq="MS",
        )

        absent_months = expected_periods.difference(valid_periods)

        print(f"Missing months in timeline: {len(absent_months)}")

        if len(absent_months):
            warnings.append(
                "The overall timeline contains missing months"
            )

    # Validate product identifiers.
    codes = df["product_code"]

    missing_codes = int(
        (codes.isna() | codes.str.strip().eq("").fillna(False)).sum()
    )

    print("\n=== PRODUCT VALIDATION ===")
    print(f"Distinct product codes: {codes.nunique()}")
    print(f"Missing product codes: {missing_codes}")

    if missing_codes:
        errors.append("Missing product identifiers")

    # Check the logical key: one product per month.
    key_data = pd.DataFrame(
        {
            "product_code": codes,
            "period": parsed_period,
        }
    )

    duplicated_mask = key_data.duplicated(
        subset=["product_code", "period"],
        keep=False,
    )

    duplicate_rows = int(duplicated_mask.sum())

    duplicate_groups = int(
        key_data.loc[duplicated_mask]
        .drop_duplicates()
        .shape[0]
    )

    print("\n=== DUPLICATE CHECK ===")
    print(f"Rows involved in duplicate keys: {duplicate_rows}")
    print(f"Duplicate product-month keys: {duplicate_groups}")

    if duplicate_groups:
        errors.append("Duplicate product-month records")

    # Validate numeric prices separately from missing prices.
    raw_price = df["average_price_uzs_per_kg"]

    price = pd.to_numeric(
        raw_price,
        errors="coerce",
    )

    invalid_prices = int(
        (raw_price.notna() & price.isna()).sum()
    )

    missing_prices = int(price.isna().sum())

    negative_prices = int(price.lt(0).fillna(False).sum())
    zero_prices = int(price.eq(0).fillna(False).sum())

    print("\n=== PRICE VALIDATION ===")
    print(f"Missing prices: {missing_prices}")
    print(f"Invalid non-numeric prices: {invalid_prices}")
    print(f"Negative prices: {negative_prices}")
    print(f"Zero prices: {zero_prices}")

    # Investigate zero-price observations before changing them.
    zero_rows = df.loc[
        price.eq(0),
        [
            "product_code",
            "product_name_en",
            "period",
            "average_price_uzs_per_kg",
            "source_snapshot",
        ],
    ]

    if not zero_rows.empty:
        print("\n=== ZERO-PRICE OBSERVATIONS ===")
        print(zero_rows.to_string(index=False))


    valid_prices = price.dropna()

    if not valid_prices.empty:
        print(f"Minimum price: {valid_prices.min():,.2f}")
        print(f"Median price: {valid_prices.median():,.2f}")
        print(f"Maximum price: {valid_prices.max():,.2f}")

    if invalid_prices or negative_prices:
        errors.append("Invalid numeric price values")

    if missing_prices:
        warnings.append(
            "Some price values are missing and need investigation"
        )

    if zero_prices:
        warnings.append(
            "Zero prices should be checked against source semantics"
        )

    # Test completeness of the product-month combinations.
    product_count = codes.nunique()
    period_count = len(valid_periods)

    expected_combinations = product_count * period_count

    valid_key_data = key_data.dropna(
        subset=["product_code", "period"]
    )

    observed_combinations = len(
        valid_key_data.drop_duplicates()
    )

    missing_combinations = max(
        0,
        expected_combinations - observed_combinations,
    )

    print("\n=== COVERAGE CHECK ===")
    print(f"Expected combinations: {expected_combinations:,}")
    print(f"Observed combinations: {observed_combinations:,}")
    print(f"Missing combinations: {missing_combinations:,}")

    if missing_combinations:
        warnings.append(
            "Some product-month combinations are absent"
        )

    # Summarize how many observations each product has.
    rows_per_product = df.groupby(
        "product_code",
        dropna=False,
    ).size()

    if not rows_per_product.empty:
        print("\n=== OBSERVATIONS PER PRODUCT ===")
        print(f"Minimum: {rows_per_product.min()}")
        print(f"Median: {rows_per_product.median():.1f}")
        print(f"Maximum: {rows_per_product.max()}")

    # Final result: warnings require investigation;
    # errors mean this dataset should not pass the quality gate.
    print("\n=== AUDIT RESULT ===")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"  ERROR: {error}")

    if warnings:
        for warning in warnings:
            print(f"  WARNING: {warning}")

    if not errors and not warnings:
        print("PASS: All current checks passed.")
    elif not errors:
        print("PASS WITH WARNINGS: Review the findings above.")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
