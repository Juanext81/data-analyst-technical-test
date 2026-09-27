-- Part 1 — SQL queries

-- 1. Los 10 clientes con más pedidos
SELECT
    c.customer_id,
    c.first_name,
    c.last_name,
    COUNT(o.order_id) AS total_orders
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.first_name, c.last_name
ORDER BY total_orders DESC
LIMIT 10;


-- 2. Revenue total (quantity × price) por categoría de producto
SELECT
    cat.category_name,
    SUM(od.quantity * od.unit_price) AS total_revenue
FROM order_details od
JOIN products p ON p.product_id = od.product_id
JOIN categories cat ON cat.category_id = p.category_id
GROUP BY cat.category_name
ORDER BY total_revenue DESC;


-- 3. Clientes que nunca han hecho un pedido (CTE + NOT EXISTS)
WITH customer_orders AS (
    SELECT DISTINCT customer_id
    FROM orders
)
SELECT c.customer_id, c.first_name, c.last_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1 FROM customer_orders co WHERE co.customer_id = c.customer_id
);


-- 4. Revenue acumulado mes a mes por cliente (running total)
WITH monthly_revenue AS (
    SELECT
        o.customer_id,
        DATE_TRUNC('month', o.order_date) AS month,
        SUM(od.quantity * od.unit_price) AS revenue
    FROM orders o
    JOIN order_details od ON od.order_id = o.order_id
    GROUP BY o.customer_id, DATE_TRUNC('month', o.order_date)
)
SELECT
    customer_id,
    month,
    revenue,
    SUM(revenue) OVER (
        PARTITION BY customer_id
        ORDER BY month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM monthly_revenue
ORDER BY customer_id, month;


-- 5. Detección de datos sucios: precio 0 o cantidad negativa
SELECT
    od.order_detail_id,
    od.order_id,
    od.product_id,
    od.quantity,
    od.unit_price
FROM order_details od
WHERE od.unit_price = 0
   OR od.quantity < 0;


