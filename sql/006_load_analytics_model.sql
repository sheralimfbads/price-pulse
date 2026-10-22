
BEGIN;


-- 1. Populate the product dimension.
-- For now, changing product descriptions updates the existing row.
-- This is a Type 1 dimension update, not historical tracking.

INSERT INTO analytics.dim_product (
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic
)
SELECT DISTINCT
    product_code,
    product_name_uz,
    product_name_ru,
    product_name_en,
    product_name_uz_cyrillic
FROM staging.official_price_observations
WHERE true

ON CONFLICT (product_code)
DO UPDATE SET
    product_name_uz = EXCLUDED.product_name_uz,
    product_name_ru = EXCLUDED.product_name_ru,
    product_name_en = EXCLUDED.product_name_en,
    product_name_uz_cyrillic = EXCLUDED.product_name_uz_cyrillic;


-- 2. Populate the monthly dimension.

INSERT INTO analytics.dim_month (
    month_key,
    month_start,
    calendar_year,
    quarter_number,
    month_number
)
SELECT DISTINCT
    (
        EXTRACT(YEAR FROM period)::INTEGER * 100
        + EXTRACT(MONTH FROM period)::INTEGER
    ) AS month_key,

    period AS month_start,
    EXTRACT(YEAR FROM period)::SMALLINT AS calendar_year,
    EXTRACT(QUARTER FROM period)::SMALLINT AS quarter_number,
    EXTRACT(MONTH FROM period)::SMALLINT AS month_number

FROM staging.official_price_observations
WHERE true

ON CONFLICT (month_key)
DO NOTHING;


-- 3. Populate the fact table.
-- Join the staging records to dimensions to retrieve their keys.

INSERT INTO analytics.fact_monthly_official_price (
    product_key,
    month_key,
    source_price_uzs_per_kg,
    average_price_uzs_per_kg,
    price_status,
    source_fetched_at_utc,
    source_snapshot
)
SELECT
    dp.product_key,
    dm.month_key,
    s.source_price_uzs_per_kg,
    s.average_price_uzs_per_kg,
    s.price_status,
    s.source_fetched_at_utc,
    s.source_snapshot

FROM staging.official_price_observations AS s

JOIN analytics.dim_product AS dp
    ON dp.product_code = s.product_code

JOIN analytics.dim_month AS dm
    ON dm.month_start = s.period

ON CONFLICT (product_key, month_key)
DO UPDATE SET
    source_price_uzs_per_kg = EXCLUDED.source_price_uzs_per_kg,
    average_price_uzs_per_kg = EXCLUDED.average_price_uzs_per_kg,
    price_status = EXCLUDED.price_status,
    source_fetched_at_utc = EXCLUDED.source_fetched_at_utc,
    source_snapshot = EXCLUDED.source_snapshot;


COMMIT;
