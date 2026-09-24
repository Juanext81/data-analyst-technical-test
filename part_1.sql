-- =============================================================
-- Part 1 — SQL queries
-- Target: PostgreSQL (the ecomerce database on Amazon RDS)
--
-- Schema reference:
--   categories(category_id PK, category_name)
--   customers(customer_id PK, first_name, last_name, email, city, registration_date)
--   products(product_id PK, product_name, category_id FK, price, stock)
--   orders(order_id PK, customer_id FK, order_date, status, payment_method)
--   order_details(order_detail_id PK, order_id FK, product_id FK, quantity, unit_price)
--
-- Notes:
--   * Revenue = SUM(quantity * unit_price) from order_details.
--   * status/payment_method may contain intentional data-quality defects
--     (NULLs and inconsistent casing/whitespace, e.g. '  ReTuRnEd ').
--     Use TRIM(LOWER(status)) when filtering by status.
-- =============================================================


-- Write your queries below.

