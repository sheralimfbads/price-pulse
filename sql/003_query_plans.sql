---  \d staging.official_price_observations

--
ANALYZE staging.official_price_observations;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_code,
    period,
    average_price_uzs_per_kg
FROM staging.official_price_observations
WHERE product_code = '001'
ORDER BY period DESC
LIMIT 12;


--
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_code,
    period,
    average_price_uzs_per_kg
FROM staging.official_price_observations
WHERE period >= DATE '2026-01-01'
ORDER BY period;


