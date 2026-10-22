
CREATE SCHEMA IF NOT EXISTS analytics;


-- One row per product.
CREATE TABLE IF NOT EXISTS analytics.dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code TEXT NOT NULL UNIQUE,

    product_name_uz TEXT,
    product_name_ru TEXT,
    product_name_en TEXT,
    product_name_uz_cyrillic TEXT
);


-- One row per month.
-- month_key uses YYYYMM format, e.g. 202609.
CREATE TABLE IF NOT EXISTS analytics.dim_month (
    month_key INTEGER PRIMARY KEY,
    month_start DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    quarter_number SMALLINT NOT NULL,
    month_number SMALLINT NOT NULL,

    CONSTRAINT ck_month_start
        CHECK (EXTRACT(DAY FROM month_start) = 1),

    CONSTRAINT ck_month_number
        CHECK (month_number BETWEEN 1 AND 12),

    CONSTRAINT ck_quarter_number
        CHECK (quarter_number BETWEEN 1 AND 4),

    CONSTRAINT ck_month_key
        CHECK (
            month_key =
                calendar_year::INTEGER * 100
                + month_number::INTEGER
        ),

    CONSTRAINT ck_calendar_attributes
        CHECK (
            calendar_year = EXTRACT(YEAR FROM month_start)::SMALLINT
            AND month_number = EXTRACT(MONTH FROM month_start)::SMALLINT
            AND quarter_number = EXTRACT(QUARTER FROM month_start)::SMALLINT
        )
);


-- One row per product per month.
CREATE TABLE IF NOT EXISTS analytics.fact_monthly_official_price (
    product_key BIGINT NOT NULL
        REFERENCES analytics.dim_product(product_key),

    month_key INTEGER NOT NULL
        REFERENCES analytics.dim_month(month_key),

    source_price_uzs_per_kg NUMERIC(14, 2),
    average_price_uzs_per_kg NUMERIC(14, 2),

    price_status TEXT NOT NULL,

    source_fetched_at_utc TIMESTAMPTZ NOT NULL,
    source_snapshot TEXT NOT NULL,

    CONSTRAINT pk_fact_monthly_official_price
        PRIMARY KEY (product_key, month_key),

    CONSTRAINT ck_fact_source_price
        CHECK (
            source_price_uzs_per_kg IS NULL
            OR source_price_uzs_per_kg >= 0
        ),

    CONSTRAINT ck_fact_analytical_price
        CHECK (
            average_price_uzs_per_kg IS NULL
            OR average_price_uzs_per_kg >= 0
        ),

    CONSTRAINT ck_fact_price_status
        CHECK (
            price_status IN (
                'observed',
                'zero_marked_unavailable',
                'missing_in_source'
            )
        ),

    CONSTRAINT ck_fact_price_consistency
        CHECK (
            (
                price_status = 'observed'
                AND source_price_uzs_per_kg > 0
                AND average_price_uzs_per_kg IS NOT NULL
                AND average_price_uzs_per_kg =
                    source_price_uzs_per_kg
            )
            OR
            (
                price_status = 'zero_marked_unavailable'
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
