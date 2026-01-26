-- ForecastLabAI KPI Query Examples
-- These queries demonstrate common analytical patterns

-- =============================================================================
-- Daily Sales Summary by Store
-- =============================================================================
SELECT
    s.date,
    st.code AS store_code,
    st.name AS store_name,
    COUNT(DISTINCT s.product_id) AS products_sold,
    SUM(s.quantity) AS total_units,
    SUM(s.total_amount) AS total_revenue
FROM sales_daily s
JOIN store st ON s.store_id = st.id
WHERE s.date BETWEEN '2024-01-01' AND '2024-01-31'
GROUP BY s.date, st.code, st.name
ORDER BY s.date, total_revenue DESC;

-- =============================================================================
-- Weekly Sales Trend by Category
-- =============================================================================
SELECT
    DATE_TRUNC('week', s.date) AS week_start,
    p.category,
    SUM(s.quantity) AS total_units,
    SUM(s.total_amount) AS total_revenue,
    AVG(s.unit_price) AS avg_price
FROM sales_daily s
JOIN product p ON s.product_id = p.id
WHERE s.date >= CURRENT_DATE - INTERVAL '12 weeks'
GROUP BY DATE_TRUNC('week', s.date), p.category
ORDER BY week_start, p.category;

-- =============================================================================
-- Top 10 Products by Revenue (Last 30 Days)
-- =============================================================================
SELECT
    p.sku,
    p.name,
    p.category,
    SUM(s.quantity) AS total_units,
    SUM(s.total_amount) AS total_revenue,
    RANK() OVER (ORDER BY SUM(s.total_amount) DESC) AS revenue_rank
FROM sales_daily s
JOIN product p ON s.product_id = p.id
WHERE s.date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY p.sku, p.name, p.category
ORDER BY total_revenue DESC
LIMIT 10;

-- =============================================================================
-- Year-over-Year Growth by Store
-- =============================================================================
WITH current_year AS (
    SELECT
        store_id,
        SUM(total_amount) AS revenue
    FROM sales_daily
    WHERE date >= DATE_TRUNC('year', CURRENT_DATE)
    GROUP BY store_id
),
prior_year AS (
    SELECT
        store_id,
        SUM(total_amount) AS revenue
    FROM sales_daily
    WHERE date >= DATE_TRUNC('year', CURRENT_DATE) - INTERVAL '1 year'
      AND date < DATE_TRUNC('year', CURRENT_DATE)
    GROUP BY store_id
)
SELECT
    st.code AS store_code,
    st.name AS store_name,
    cy.revenue AS current_year_revenue,
    py.revenue AS prior_year_revenue,
    ROUND((cy.revenue - py.revenue) / NULLIF(py.revenue, 0) * 100, 2) AS yoy_growth_pct
FROM current_year cy
JOIN prior_year py ON cy.store_id = py.store_id
JOIN store st ON cy.store_id = st.id
ORDER BY yoy_growth_pct DESC;

-- =============================================================================
-- Daily Sales with Calendar Attributes (Day-of-Week Analysis)
-- =============================================================================
SELECT
    c.day_of_week,
    CASE c.day_of_week
        WHEN 0 THEN 'Monday'
        WHEN 1 THEN 'Tuesday'
        WHEN 2 THEN 'Wednesday'
        WHEN 3 THEN 'Thursday'
        WHEN 4 THEN 'Friday'
        WHEN 5 THEN 'Saturday'
        WHEN 6 THEN 'Sunday'
    END AS day_name,
    COUNT(DISTINCT s.date) AS num_days,
    AVG(daily_revenue) AS avg_daily_revenue
FROM (
    SELECT
        date,
        SUM(total_amount) AS daily_revenue
    FROM sales_daily
    WHERE date >= CURRENT_DATE - INTERVAL '90 days'
    GROUP BY date
) s
JOIN calendar c ON s.date = c.date
GROUP BY c.day_of_week
ORDER BY c.day_of_week;

-- =============================================================================
-- Holiday vs Non-Holiday Revenue Comparison
-- =============================================================================
SELECT
    CASE WHEN c.is_holiday THEN 'Holiday' ELSE 'Regular Day' END AS day_type,
    COUNT(DISTINCT s.date) AS num_days,
    SUM(s.total_amount) AS total_revenue,
    AVG(s.total_amount) AS avg_revenue_per_record,
    SUM(s.quantity) AS total_units
FROM sales_daily s
JOIN calendar c ON s.date = c.date
WHERE s.date >= CURRENT_DATE - INTERVAL '365 days'
GROUP BY c.is_holiday
ORDER BY c.is_holiday DESC;

-- =============================================================================
-- Store Performance Quartiles
-- =============================================================================
WITH store_revenue AS (
    SELECT
        store_id,
        SUM(total_amount) AS total_revenue
    FROM sales_daily
    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY store_id
)
SELECT
    st.code AS store_code,
    st.name AS store_name,
    st.region,
    sr.total_revenue,
    NTILE(4) OVER (ORDER BY sr.total_revenue) AS performance_quartile
FROM store_revenue sr
JOIN store st ON sr.store_id = st.id
ORDER BY sr.total_revenue DESC;

-- =============================================================================
-- Product Category Mix by Store
-- =============================================================================
SELECT
    st.code AS store_code,
    p.category,
    SUM(s.total_amount) AS category_revenue,
    SUM(s.total_amount) * 100.0 / SUM(SUM(s.total_amount)) OVER (PARTITION BY st.code) AS revenue_share_pct
FROM sales_daily s
JOIN store st ON s.store_id = st.id
JOIN product p ON s.product_id = p.id
WHERE s.date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY st.code, p.category
ORDER BY st.code, category_revenue DESC;
