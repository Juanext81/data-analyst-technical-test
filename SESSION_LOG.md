# Session Log — E-commerce Database (AWS)

A reconstructed log of the working session that built and deployed the
e-commerce dataset project for the data analyst technical test. This
summarizes the work, decisions, and troubleshooting; it is not a verbatim
chat transcript.

## Goal

Create an e-commerce dataset project: a relational PostgreSQL schema, a
deterministic Python data generator (30 customers, 4 categories, 15 products,
100 orders, 250 order-detail rows, dates across the last 12 months, plus a few
intentional data-quality defects), host the database on Amazon RDS, connect the
repo to it, and load the data.

## 1. Project bootstrap (pre-spec)

- Reviewed the existing `schema.sql` and wrote an initial `README.md`.
- Added a `queries.sql` with analysis queries, then converted the notebook
  `generate_data.py.ipynb` into a plain script `generate_data.py`
  (fixing the `__file__`/`Path` output-dir issue in the process).

## 2. Spec workflow (Kiro spec: `ecommerce-database-aws`)

Chose a **feature**, **requirements-first** spec.

- **requirements.md** — 11 requirements in EARS form (schema, data volume, date
  distribution, intentional defects, historical price accuracy, CSV export, AWS
  provisioning, repo connection, data loading, analysis queries, documentation).
  Each requirement was refined for testability. The user then **removed
  Requirement 10 (Analysis Queries)**; Documentation was renumbered to 10 and
  the `Analysis_Queries` glossary term dropped.
- **design.md** — architecture (generator → CSVs → loader → RDS), components and
  interfaces, data models with constraints, 16 correctness properties, error
  handling, and a testing strategy (Hypothesis for property tests).
- **tasks.md** — 15 top-level tasks with a wave-based dependency graph.

## 3. Implementation (executed task by task)

| Task | Result |
| ---- | ------ |
| 1. Scaffolding | `db/`, `tests/`, `data/`, `requirements.txt` (pandas, psycopg2-binary, python-dotenv, hypothesis, pytest), `pytest.ini`, `.venv` |
| 2.1 Schema constraints | `schema.sql` extended: NOT NULL, UNIQUE(email), CHECK(price/unit_price/quantity/stock >= 0), DECIMAL(12,2), 4 FKs |
| 3.1 Generator scaffolding | `generate()` entry point, `DefectRecord`/`DefectSummary`/`GenerationResult`, `GenerationError`, single seeded RNG |
| 4.1 Categories + customers | 4 categories, 30 customers with unique emails, registration dates in last 365 days |
| 4.2 Products | 15 products, every category covered, valid category FK |
| 4.3 Orders | 100 orders, 12-month distribution (>=1/month, <=40/month), order_date on/after registration |
| 4.4 Order details | 250 rows, valid FKs, unit_price snapshot (immutable to later price changes) |
| 5.1 Referential integrity | In-memory FK validation before any write; unresolved/price-less product rejected |
| 6.1 CSV export | 5 CSVs to `data/`, headers, dir creation, overwrite, empty cell for NULL, per-file write-error reporting |
| 7.1 Defect injection | NULL + inconsistent defects into nullable non-key columns only (city, status, payment_method, stock); caps floor(10%) per table; defect summary |
| 8.1 Compose generate() | Builders → validate → inject → write; returns GenerationResult. Verified: 4/30/15/100/250, 14 defects, byte-identical across runs |
| 9. Checkpoint | Generator verified end to end |
| 10.1 Connection | `db/connection.py`: REQUIRED_PARAMS, load_config, connect (10s timeout, SELECT 1), no secret leakage |
| 10.2 .env template | `.env.example` (placeholders) + `.gitignore` entry for `.env` |
| 11.1 Loader | `load_data.py`: FK-safe LOAD_ORDER, empty→NULL, per-file transactions, FK-violation + missing-file + row-count reporting; 9 unit tests pass |
| 12. Checkpoint | Connection + loader tests pass |
| 13.1 Documentation | `README.md` rewritten with the full reproduce flow and documented defects |
| 14.1 AWS provisioning + schema | RDS PostgreSQL provisioned; `schema.sql` applied: 5 tables + 4 FKs |
| 14.2 AWS integration | End-to-end load verified live against RDS |
| 15. Final checkpoint | All 9 tests pass; live pipeline verified |

Optional property-based tests (Hypothesis) and example-based unit tests were
deliberately skipped.

## 4. AWS provisioning and troubleshooting

Provisioned an Amazon RDS PostgreSQL instance (`ecomerce-test`) via the console.
Connecting from the local machine required several fixes, in order:

1. **Private-IP timeout** — endpoint resolved to `172.31.x.x`; the instance was
   not publicly accessible. Enabled **Public access = Yes**.
2. **Security group** — added an inbound rule allowing TCP 5432 from the
   developer's IP.
3. **SSL stall** — the default `sslmode` caused the connect to hang until
   timeout. **Fixed `db/connection.py` to use `sslmode="require"`** (RDS needs
   SSL). TCP reachability confirmed with `nc` before this fix.
4. **Auth failure** — password mismatch; reset the RDS master password and
   updated `.env`.
5. **Missing database** — RDS had only the default `postgres` DB (no initial DB
   name set at launch). Created the `ecomerce` database.

After these, the connection layer connected to `ecomerce` on PostgreSQL 18.3.

## 5. Deployment verification (live RDS)

- `schema.sql` applied: 5 tables (categories, customers, products, orders,
  order_details) + 4 foreign keys.
- `python load_data.py --data-dir data --env .env` loaded all rows:

  ```
  categories: 4    customers: 30    products: 15
  orders: 100      order_details: 250    total: 399
  ```

- Intentional NULL defects confirmed in the database (empty CSV cells mapped to
  real SQL NULL, not empty strings): customers.city NULL = 1, orders.status
  NULL = 4, products.stock NULL = 1.

## 6. Notes / follow-ups

- The RDS instance is **billable** — stop or delete it when finished.
- `.env` holds real credentials and is gitignored (never committed).
- Optional Hypothesis property tests remain available to add if desired.
