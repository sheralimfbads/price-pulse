
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.official_price_observations (
    product_code TEXT NOT NULL,
    product_name_uz TEXT,
    product_name_ru TEXT,
    product_name_en TEXT,
    product_name_uz_cyrillic TEXT,
    period DATE NOT NULL,
    source_price_uzs_per_kg NUMERIC(14, 2),
    source_fetched_at_utc TIMESTAMPTZ NOT NULL,
    source_snapshot TEXT NOT NULL,
    average_price_uzs_per_kg NUMERIC(14, 2),
    price_status TEXT NOT NULL,

    CONSTRAINT pk_official_price_observations
        PRIMARY KEY (product_code, period),

    CONSTRAINT ck_period_month_start
        CHECK (EXTRACT(DAY FROM period) = 1),

    CONSTRAINT ck_source_price_nonnegative
        CHECK (
            source_price_uzs_per_kg IS NULL
            OR source_price_uzs_per_kg >= 0
        ),

    CONSTRAINT ck_analytical_price_nonnegative
        CHECK (
            average_price_uzs_per_kg IS NULL
            OR average_price_uzs_per_kg >= 0
        ),

    CONSTRAINT ck_price_status
        CHECK (
            price_status IN (
                'observed',
                'zero_marked_unavailable',
                'missing_in_source'
            )
        ),

    CONSTRAINT ck_price_status_consistency
        CHECK (
            (
                price_status = 'observed'
                AND source_price_uzs_per_kg IS NOT NULL
                AND source_price_uzs_per_kg > 0
                AND average_price_uzs_per_kg IS NOT NULL
                AND average_price_uzs_per_kg =
                    source_price_uzs_per_kg
            )
            OR
            (
                price_status = 'zero_marked_unavailable'
                AND source_price_uzs_per_kg IS NOT NULL
                AND source_price_uzs_per_kg = 0
                AND average_price_uzs_per_kg IS NULL
            )
            OR
            (
                price_status = 'missing_in_source'
                AND source_price_uzs_per_kg IS NULL
                AND average_price_uzs_per_kg IS NULL
            )
        )
);
