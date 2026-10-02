# Part 3 — AI-Assisted Analysis Review

## Question

Which city generates the highest average revenue per customer?

## AI-generated SQL

```sql
WITH customer_revenue AS (
    SELECT
        c.customer_id,
        c.city,
        SUM(od.quantity * od.unit_price) AS total_revenue
    FROM customers c
    JOIN orders o
        ON o.customer_id = c.customer_id
    JOIN order_details od
        ON od.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY c.customer_id, c.city
)
SELECT
    city,
    AVG(total_revenue) AS average_revenue_per_customer
FROM customer_revenue
WHERE city IS NOT NULL
GROUP BY city
ORDER BY average_revenue_per_customer DESC
LIMIT 1;
```

## Review of the AI Result

The query correctly calculates revenue at the customer level before calculating the average by city. This prevents order-detail rows from incorrectly affecting the customer-level average.

However, the original query uses `INNER JOIN`s and therefore excludes customers who do not have completed orders. If "average revenue per customer" means the average across all customers in each city, those customers should be included with a revenue value of zero.

## Corrected SQL

```sql
WITH customer_revenue AS (
    SELECT
        c.customer_id,
        c.city,
        COALESCE(
            SUM(
                CASE
                    WHEN o.status = 'completed'
                    THEN od.quantity * od.unit_price
                    ELSE 0
                END
            ),
            0
        ) AS total_revenue
    FROM customers c
    LEFT JOIN orders o
        ON o.customer_id = c.customer_id
    LEFT JOIN order_details od
        ON od.order_id = o.order_id
    GROUP BY
        c.customer_id,
        c.city
)
SELECT
    city,
    AVG(total_revenue) AS average_revenue_per_customer
FROM customer_revenue
WHERE city IS NOT NULL
GROUP BY city
ORDER BY average_revenue_per_customer DESC
LIMIT 1;
```

## Manual Verification

I trusted the AI when it correctly identified that revenue should first be calculated at the customer level before averaging by city. I manually verified the joins because joining orders and order_details can easily duplicate or distort revenue if the aggregation level is wrong. I also checked how customers with no completed orders were handled and found that the original `INNER JOIN` excluded them. I therefore changed the query to use `LEFT JOIN`s and `COALESCE` so that those customers are included with zero revenue.