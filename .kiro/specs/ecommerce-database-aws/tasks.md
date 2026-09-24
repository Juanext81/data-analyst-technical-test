# Implementation Plan: E-commerce Database (AWS)

## Overview

This plan implements the e-commerce dataset project incrementally in Python 3.9+ (pandas, psycopg2, python-dotenv), backed by PostgreSQL on Amazon RDS, with Hypothesis for property-based testing.

Work proceeds from the schema and project scaffolding, through the deterministic data generator (builders, date distribution, price snapshotting, referential-integrity validation, CSV export, and defect injection), then the connection layer and loader, and finally documentation and AWS provisioning/integration. Property tests are placed close to the code they validate so invariants are caught early. Each task references the requirements and/or design correctness properties it satisfies.

Property test tasks are tagged in code with the format **Feature: ecommerce-database-aws, Property {number}: {property_text}** per the design Testing Strategy.

## Tasks

- [x] 1. Set up project scaffolding and dependencies
  - Create package directories (`db/`, `tests/`) and `data/` output target
  - Add a `requirements.txt` (or `pyproject.toml`) pinning pandas, psycopg2-binary, python-dotenv, hypothesis, pytest
  - Configure a pytest setup so tests are discoverable
  - _Requirements: 6.2, 6.4_

- [x] 2. Extend the database schema with integrity constraints
  - [x] 2.1 Add refined constraints to `schema.sql`
    - Add `NOT NULL` to mandatory columns per the Data Models (customers: customer_id, first_name, last_name, email; categories: category_id, category_name; products: product_id, product_name, category_id, price; orders: order_id, customer_id, order_date; order_details: order_detail_id, order_id, product_id, quantity, unit_price)
    - Add `UNIQUE` on `customers.email`
    - Add `CHECK (price >= 0)`, `CHECK (unit_price >= 0)`, `CHECK (quantity >= 0)`, `CHECK (stock >= 0)`
    - Keep `price`/`unit_price` as `DECIMAL(12,2)` and retain the four existing foreign keys
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12_

  - [ ]* 2.2 Write property test for schema rejecting negative numeric values
    - **Property 13: Schema rejects negative numeric values**
    - Apply `schema.sql` to an ephemeral/local PostgreSQL (test container) and assert negative `price`, `unit_price`, `quantity`, `stock` inserts are rejected and leave contents unchanged
    - **Validates: Requirements 1.12**

  - [ ]* 2.3 Write smoke test for schema catalog
    - Inspect the applied catalog to confirm the five tables, columns/types, NOT NULL, UNIQUE(email), and the four FKs
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11_

- [x] 3. Implement generator scaffolding and data models
  - [x] 3.1 Create the generator entry point and supporting models in `generate_data.py`
    - Define `generate(seed=42, output_dir="data", generation_date=None) -> GenerationResult`
    - Define `DefectRecord`, `DefectSummary`, `GenerationResult` dataclasses and `GenerationError`
    - Seed a single RNG from `seed` so all downstream draws are stable/ordered
    - _Requirements: 2.7_

- [x] 4. Implement deterministic table builders
  - [x] 4.1 Implement `build_categories` and `build_customers`
    - `build_categories(rng)` produces exactly 4 rows with unique ids
    - `build_customers(rng, generation_date)` produces exactly 30 rows with unique ids and `registration_date` within the last 365 days (inclusive)
    - _Requirements: 2.1, 2.2, 3.1, 2.9_

  - [x] 4.2 Implement `build_products`
    - Produce exactly 15 rows; assign every one of the 4 categories at least 1 product; each product in exactly one category via a valid category id
    - _Requirements: 2.3, 2.6_

  - [x] 4.3 Implement `build_orders` with the 12-month distribution algorithm
    - Produce exactly 100 rows, each referencing an existing customer
    - Allocate ≥1 order to each of the 12 calendar months, distribute remaining orders under the per-month cap of `floor(0.40 * 100) = 40`
    - Assign each order a concrete day within its month that is on/after the referenced customer's `registration_date` and on/before the generation date; re-pair when no valid day exists (late-registrant edge case)
    - _Requirements: 2.4, 3.2, 3.3, 3.4, 3.5, 2.9_

  - [x] 4.4 Implement `build_order_details` with unit_price snapshotting
    - Produce exactly 250 rows, each referencing an existing order and existing product
    - Snapshot `unit_price` from the referenced product's `price` at generation time, scale exactly 2 decimals
    - _Requirements: 2.5, 5.1, 5.3_

  - [ ]* 4.5 Write property test for structural volumes, key integrity, and category coverage
    - **Property 1: Structural volumes, key integrity, and category coverage**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

  - [ ]* 4.6 Write property test for dates within the last 12 months
    - **Property 3: Dates within the last 12 months**
    - **Validates: Requirements 2.9, 3.1, 3.2**

  - [ ]* 4.7 Write property test for monthly order distribution
    - **Property 4: Monthly order distribution**
    - **Validates: Requirements 3.3**

  - [ ]* 4.8 Write property test for orders dated on or after customer registration
    - **Property 5: Orders dated on or after customer registration**
    - **Validates: Requirements 3.4, 3.5**

  - [ ]* 4.9 Write property tests for unit_price snapshot and immutability
    - **Property 10: unit_price snapshots product price** (Validates: Requirements 5.1)
    - **Property 11: Snapshot price immutability** (Validates: Requirements 5.3)

  - [ ]* 4.10 Write unit test for the late-registrant edge case
    - Registration_date equal to generation_date still yields a valid order date
    - _Requirements: 3.5_

- [x] 5. Implement referential-integrity validation
  - [x] 5.1 Implement `validate_referential_integrity(tables)`
    - Raise `GenerationError` naming the violation if any FK value (product→category, order→customer, order_detail→order, order_detail→product) has no parent
    - Reject an order_detail whose product cannot be resolved or has no price, excluding the row and raising an error identifying the unresolved product, leaving prior rows unchanged
    - Run fully in memory before any file write so a failure produces zero output
    - _Requirements: 2.8, 5.2_

  - [ ]* 5.2 Write unit tests for generation error handling
    - Referential-integrity failure aborts generation with no CSV output (2.8)
    - Unresolvable/price-less product rejection leaves prior rows unchanged (5.2)
    - _Requirements: 2.8, 5.2_

- [x] 6. Implement CSV export
  - [x] 6.1 Implement `write_csvs(tables, output_dir)`
    - Write exactly five CSVs named `categories`, `products`, `customers`, `orders`, `order_details` into `data/`
    - Include a header row of column names; create `data/` if absent; overwrite stale files on re-run
    - On write failure, raise an error identifying the specific file
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 6.2 Write property test for CSV write/read round-trip
    - **Property 12: CSV write/read round-trip**
    - **Validates: Requirements 6.3**

  - [ ]* 6.3 Write unit tests for CSV export behaviors
    - Five CSVs exist with correct names (6.1, 6.2); `data/` created when absent (6.4); stale files overwritten (6.5); write-failure error names the file (6.6)
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.6_

- [x] 7. Implement intentional data-quality defect injection
  - [x] 7.1 Implement `inject_defects(rng, tables) -> DefectSummary`
    - Target only nullable non-key columns (`customers.city`, `orders.status`, `orders.payment_method`, `products.stock`)
    - Introduce at least one NULL defect and at least one inconsistent (format/unit/casing) defect
    - Cap per table at `floor(0.10 * row_count)` with at least 1 defect overall; never touch PK/FK columns
    - Record each defect (table, column, row id, type) in the `DefectSummary`; emit the summary as output
    - Ensure defect columns/rows/values are identical across runs for a fixed seed
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 7.2 Write property test for bounded defects
    - **Property 6: Data-quality defects are bounded**
    - **Validates: Requirements 4.1, 4.4**

  - [ ]* 7.3 Write property test for required defect types present
    - **Property 7: Required defect types are present**
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 7.4 Write property test for defects never touching key columns
    - **Property 8: Defects never touch key columns**
    - **Validates: Requirements 4.5**

  - [ ]* 7.5 Write property test for defect summary completeness
    - **Property 9: Defect summary completeness**
    - **Validates: Requirements 4.6**

- [x] 8. Wire the generator together and verify determinism
  - [x] 8.1 Compose `generate()` end-to-end
    - Chain builders → validation → defect injection → CSV export, returning a `GenerationResult` with the defect summary
    - _Requirements: 2.7, 4.6, 6.1_

  - [ ]* 8.2 Write property test for deterministic, byte-identical output
    - **Property 2: Deterministic, byte-identical output**
    - **Validates: Requirements 2.7, 4.7**

- [x] 9. Checkpoint - Ensure all generator tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement the repository-to-database connection layer
  - [x] 10.1 Implement `db/connection.py`
    - Define `REQUIRED_PARAMS = ["host", "port", "dbname", "user", "password"]`
    - `load_config(env_path=".env")` reads params only from `.env`/environment and raises `ConfigError` listing every missing/invalid parameter by name
    - `connect(config, timeout_seconds=10)` opens a psycopg2 connection with a 10s timeout, raising `ConnectionFailure` with a cause on unreachable host or rejected auth; return a connection whose state confirms queries can run
    - Reference credentials by name only; never echo secret values in errors/logs
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 10.2 Add `.env.example` template and `.gitignore` entry
    - Create `.env.example` listing the five parameter names with placeholder values and no real credentials
    - Add `.env` to `.gitignore` so credentials stay out of version control
    - _Requirements: 7.5, 8.1, 8.5_

  - [ ]* 10.3 Write property test for connection parameter validation
    - **Property 14: Connection parameter validation names every bad parameter**
    - **Validates: Requirements 8.3**

  - [ ]* 10.4 Write unit tests for connection config and templates
    - `.env.example` lists the five names with placeholders and no secrets (8.5); `load_config` reads from `.env` (8.1); unreachable host / bad auth fails with a cause under 10s (8.4)
    - _Requirements: 8.1, 8.4, 8.5_

- [x] 11. Implement the data loader
  - [x] 11.1 Implement `load_data.py`
    - Define `LOAD_ORDER = ["categories", "customers", "products", "orders", "order_details"]`
    - `load_all(conn, data_dir="data")` verifies all five CSVs exist before loading; loads in FK-safe order; maps empty cells for nullable columns to SQL NULL; loads each file in its own transaction
    - On FK violation, report violating table + row id and roll back that file (no partial load)
    - After loading, verify each table's loaded row count equals its source CSV data-row count and report any mismatch
    - On a missing source CSV, report the missing file and do not begin loading
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 11.2 Write property test for empty CSV cells loading as NULL
    - **Property 15: Empty CSV cells load as NULL**
    - **Validates: Requirements 9.3**

  - [ ]* 11.3 Write property test for load row-count conservation
    - **Property 16: Load row-count conservation**
    - **Validates: Requirements 9.6**

  - [ ]* 11.4 Write unit tests for loader error handling and ordering
    - `LOAD_ORDER` places parents before children (9.2); FK violation reports table + row id and leaves table unchanged (9.4); missing source file reported before any loading begins (9.5)
    - _Requirements: 9.2, 9.4, 9.5_

- [x] 12. Checkpoint - Ensure connection and loader tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Update documentation for end-to-end reproduction
  - [ ] 13.1 Update `README.md` with the full reproduce flow
    - Document generating the sample data (prerequisites, command, how to confirm the five CSVs were produced)
    - Document provisioning the AWS_Database and connecting (RDS instance identifier and engine version, publicly accessible flag, security-group inbound rule for the PostgreSQL port, required connection parameter names and where to supply them, credential storage outside source control)
    - Document the ordered load steps (FK-safe load order) and the command(s) to run/confirm the workflow
    - Document each intentional data-quality defect (affected entity, defect type, how to distinguish from an unintended error)
    - _Requirements: 7.4, 7.5, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [x] 14. AWS RDS provisioning and integration
  - [x] 14.1 Provision the RDS PostgreSQL instance and apply the schema (AWS-dependent)
    - Provision an Amazon RDS PostgreSQL instance that reaches "available" and accepts connections on its port; set publicly accessible and the security-group inbound rule for the PostgreSQL port
    - Apply `schema.sql` so the instance contains exactly the five tables and four FKs; on failure report the failing statement and leave no partially applied objects
    - _Requirements: 7.1, 7.2, 7.3_

  - [x]* 14.2 Write AWS integration tests (AWS-dependent)
    - RDS reaches "available" and accepts a connection on its port (7.1); applied schema has exactly five tables and four FKs (7.2); valid params connect within 10s and run `SELECT 1` (8.2); end-to-end generate → load → all five tables populated with matching row counts (9.1)
    - _Requirements: 7.1, 7.2, 8.2, 9.1_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (tests) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Property tests use Hypothesis with a minimum of 100 examples each and carry the tag **Feature: ecommerce-database-aws, Property {number}: {property_text}**.
- Each task references specific requirements and/or design correctness properties for traceability.
- Checkpoints ensure incremental validation before moving to the next stage.
- Tasks 14.1 and 14.2 depend on live AWS infrastructure and require valid credentials supplied via the gitignored `.env`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2.1", "3.1", "10.2"] },
    { "id": 1, "tasks": ["2.2", "2.3", "4.1", "4.2", "10.1"] },
    { "id": 2, "tasks": ["4.3", "4.5", "4.6", "10.3", "10.4"] },
    { "id": 3, "tasks": ["4.4", "4.7", "4.8", "4.10"] },
    { "id": 4, "tasks": ["4.9", "5.1"] },
    { "id": 5, "tasks": ["5.2", "6.1", "7.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "7.2", "7.3", "7.4", "7.5"] },
    { "id": 7, "tasks": ["8.1", "11.1"] },
    { "id": 8, "tasks": ["8.2", "11.2", "11.3", "11.4"] },
    { "id": 9, "tasks": ["13.1", "14.1"] },
    { "id": 10, "tasks": ["14.2"] }
  ]
}
```
