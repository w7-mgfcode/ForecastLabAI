-- ForecastLabAI Exogenous Feature Join Examples
-- Join patterns for sales + price/promo/inventory signals

-- =============================================================================
-- Sales with Active Price (Point-in-Time Join)
-- =============================================================================
SELECT
    s.date,
    s.store_id,
    s.product_id,
    s.quantity,
    s.unit_price AS sale_price,
    ph.price AS list_price,
    CASE
        WHEN ph.price IS NULL THEN NULL
        WHEN ph.price = 0 THEN 0
        ELSE
            ROUND((ph.price - s.unit_price) / ph.price * 100, 2)
    END AS discount_pct
FROM sales_daily s
LEFT JOIN price_history ph ON
    ph.product_id = s.product_id
    AND (ph.store_id IS NULL OR ph.store_id = s.store_id)
    AND s.date >= ph.valid_from
    AND (ph.valid_to IS NULL OR s.date <= ph.valid_to)
WHERE s.date BETWEEN '2024-01-01' AND '2024-01-31';

-- =============================================================================
-- Sales with Active Promotions
-- =============================================================================
SELECT
    s.date,
    s.store_id,
    s.product_id,
    s.quantity,
    s.total_amount,
    pr.name AS promo_name,
    pr.discount_pct AS promo_discount_pct,
    pr.discount_amount AS promo_discount_amount,
    CASE WHEN pr.id IS NOT NULL THEN TRUE ELSE FALSE END AS on_promotion
FROM sales_daily s
LEFT JOIN promotion pr ON
    pr.product_id = s.product_id
    AND (pr.store_id IS NULL OR pr.store_id = s.store_id)
    AND s.date BETWEEN pr.start_date AND pr.end_date
WHERE s.date BETWEEN '2024-01-01' AND '2024-01-31';

-- =============================================================================
-- Sales with Inventory Signals (Stockout Detection)
-- =============================================================================
SELECT
    s.date,
    s.store_id,
    s.product_id,
    s.quantity AS units_sold,
    inv.on_hand_qty AS eod_inventory,
    inv.is_stockout,
    CASE
        WHEN inv.on_hand_qty < s.quantity * 2 THEN 'LOW'
        WHEN inv.on_hand_qty < s.quantity * 7 THEN 'MEDIUM'
        ELSE 'OK'
    END AS inventory_status
FROM sales_daily s
LEFT JOIN inventory_snapshot_daily inv ON
    inv.date = s.date
    AND inv.store_id = s.store_id
    AND inv.product_id = s.product_id
WHERE s.date BETWEEN '2024-01-01' AND '2024-01-31';

-- =============================================================================
-- Full Feature Set for Forecasting (All Exogenous Signals)
-- =============================================================================
SELECT
    s.date,
    st.code AS store_code,
    st.region,
    st.store_type,
    p.sku,
    p.category,
    p.brand,
    c.day_of_week,
    c.month,
    c.quarter,
    c.is_holiday,
    s.quantity,
    s.unit_price,
    s.total_amount,
    ph.price AS list_price,
    COALESCE(pr.discount_pct, 0) AS promo_discount_pct,
    CASE WHEN pr.id IS NOT NULL THEN 1 ELSE 0 END AS on_promotion,
    inv.on_hand_qty,
    CASE WHEN inv.is_stockout THEN 1 ELSE 0 END AS stockout_flag
FROM sales_daily s
-- Dimension joins
JOIN store st ON s.store_id = st.id
JOIN product p ON s.product_id = p.id
JOIN calendar c ON s.date = c.date
-- Exogenous signal joins
LEFT JOIN price_history ph ON
    ph.product_id = s.product_id
    AND (ph.store_id IS NULL OR ph.store_id = s.store_id)
    AND s.date >= ph.valid_from
    AND (ph.valid_to IS NULL OR s.date <= ph.valid_to)
LEFT JOIN promotion pr ON
    pr.product_id = s.product_id
    AND (pr.store_id IS NULL OR pr.store_id = s.store_id)
    AND s.date BETWEEN pr.start_date AND pr.end_date
LEFT JOIN inventory_snapshot_daily inv ON
    inv.date = s.date
    AND inv.store_id = s.store_id
    AND inv.product_id = s.product_id
WHERE s.date BETWEEN '2024-01-01' AND '2024-01-31'
ORDER BY s.date, st.code, p.sku;

-- =============================================================================
-- Lag Features (Previous Day Sales) - TIME-SAFE Pattern
-- Uses explicit date arithmetic to ensure no future leakage
-- =============================================================================
WITH lagged_sales AS (
    SELECT
        s.date,
        s.store_id,
        s.product_id,
        s.quantity,
        LAG(s.quantity, 1) OVER (
            PARTITION BY s.store_id, s.product_id
            ORDER BY s.date
        ) AS quantity_lag_1d,
        LAG(s.quantity, 7) OVER (
            PARTITION BY s.store_id, s.product_id
            ORDER BY s.date
        ) AS quantity_lag_7d
    FROM sales_daily s
)
SELECT
    date,
    store_id,
    product_id,
    quantity,
    quantity_lag_1d,
    quantity_lag_7d
FROM lagged_sales
WHERE date BETWEEN '2024-01-08' AND '2024-01-31'
  AND quantity_lag_7d IS NOT NULL;

-- =============================================================================
-- Rolling Average Features (7-Day Moving Average) - TIME-SAFE Pattern
-- Window only looks backward from cutoff date
-- =============================================================================
WITH rolling_features AS (
    SELECT
        s.date,
        s.store_id,
        s.product_id,
        s.quantity,
        AVG(s.quantity) OVER (
            PARTITION BY s.store_id, s.product_id
            ORDER BY s.date
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS quantity_ma_7d,
        STDDEV(s.quantity) OVER (
            PARTITION BY s.store_id, s.product_id
            ORDER BY s.date
            ROWS BETWEEN 7 PRECEDING AND 1 PRECEDING
        ) AS quantity_std_7d
    FROM sales_daily s
)
SELECT
    date,
    store_id,
    product_id,
    quantity,
    ROUND(quantity_ma_7d::numeric, 2) AS quantity_ma_7d,
    ROUND(quantity_std_7d::numeric, 2) AS quantity_std_7d
FROM rolling_features
WHERE date BETWEEN '2024-01-08' AND '2024-01-31';

-- =============================================================================
-- Promotional Lift Analysis
-- Compare sales during promotion vs. baseline
-- =============================================================================
WITH promo_sales AS (
    SELECT
        p.sku,
        p.name AS product_name,
        pr.name AS promo_name,
        pr.start_date,
        pr.end_date,
        SUM(s.quantity) AS promo_units,
        COUNT(DISTINCT s.date) AS promo_days
    FROM sales_daily s
    JOIN product p ON s.product_id = p.id
    JOIN promotion pr ON
        pr.product_id = s.product_id
        AND (pr.store_id IS NULL OR pr.store_id = s.store_id)
        AND s.date BETWEEN pr.start_date AND pr.end_date
    GROUP BY p.sku, p.name, pr.name, pr.start_date, pr.end_date
),
baseline_sales AS (
    SELECT
        p.sku,
        AVG(s.quantity) AS baseline_daily_units
    FROM sales_daily s
    JOIN product p ON s.product_id = p.id
    LEFT JOIN promotion pr ON
        pr.product_id = s.product_id
        AND (pr.store_id IS NULL OR pr.store_id = s.store_id)
        AND s.date BETWEEN pr.start_date AND pr.end_date
    WHERE pr.id IS NULL  -- Not on promotion
    GROUP BY p.sku
)
SELECT
    ps.sku,
    ps.product_name,
    ps.promo_name,
    ps.promo_units,
    ps.promo_days,
    ROUND(ps.promo_units::numeric / ps.promo_days, 2) AS promo_daily_avg,
    ROUND(bs.baseline_daily_units::numeric, 2) AS baseline_daily_avg,
    ROUND(
        ((ps.promo_units::numeric / ps.promo_days) - bs.baseline_daily_units)
        / NULLIF(bs.baseline_daily_units, 0) * 100,
        2
    ) AS lift_pct
FROM promo_sales ps
JOIN baseline_sales bs ON ps.sku = bs.sku
ORDER BY lift_pct DESC;

-- =============================================================================
-- Stockout Impact Analysis
-- Estimate lost sales due to stockouts
-- =============================================================================
WITH daily_avg AS (
    SELECT
        store_id,
        product_id,
        AVG(quantity) AS avg_daily_qty
    FROM sales_daily
    GROUP BY store_id, product_id
)
SELECT
    inv.date,
    st.code AS store_code,
    p.sku,
    inv.is_stockout,
    COALESCE(s.quantity, 0) AS actual_sales,
    da.avg_daily_qty AS expected_sales,
    CASE
        WHEN inv.is_stockout THEN ROUND(da.avg_daily_qty - COALESCE(s.quantity, 0), 0)
        ELSE 0
    END AS estimated_lost_sales
FROM inventory_snapshot_daily inv
JOIN store st ON inv.store_id = st.id
JOIN product p ON inv.product_id = p.id
JOIN daily_avg da ON
    da.store_id = inv.store_id
    AND da.product_id = inv.product_id
LEFT JOIN sales_daily s ON
    s.date = inv.date
    AND s.store_id = inv.store_id
    AND s.product_id = inv.product_id
WHERE inv.is_stockout = TRUE
ORDER BY estimated_lost_sales DESC
LIMIT 100;
