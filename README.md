# Data Analyst Technical Test — E-commerce Dataset

A small e-commerce data project built for a data analyst technical test. It defines a relational PostgreSQL schema, generates realistic and reproducible sample data with Python, hosts the database on Amazon RDS, and loads the generated data into it.

## What this project does

1. Defines an e-commerce database schema (`schema.sql`).
2. Generates reproducible sample data with a Python script (`generate_data.py`), exported as five CSV files under `data/`. The data includes a handful of intentional data-quality defects for cleaning practice.
3. Provisions a PostgreSQL database on Amazon RDS and connects to it from the repository (`db/connection.py`).
4. Loads the generated CSVs into the hosted database in a foreign-key-safe order (`load_data.py`).

## Dataset overview

The generated dataset contains:

| Entity        | Count | Notes                                       |
| ------------- | ----- | ------------------------------------------- |
| Customers     | 30    | Names, email, city, registration date       |
| Categories    | 4     | Electronics, Home, Sports, Accessories       |
| Products      | 15    | Spread across the 4 categories               |
| Orders        | 100   | With status and payment method               |
| Order details | 250   | Line items linking orders to products        |

Registration and order dates are spread across the 365 days preceding the generation date (inclusive). Every one of the 12 calendar months in that window contains at least one order, and no single month holds more than 40% of all orders.

## Database schema

Five tables with foreign key relationships (`schema.sql`, PostgreSQL syntax):

- **customers** — `customer_id` (PK), `first_name`, `last_name`, `email` (UNIQUE), `city`, `registration_date`
- **categories** — `category_id` (PK), `category_name`
- **products** — `product_id` (PK), `product_name`, `category_id` (FK → categories), `price`, `stock`
- **orders** — `order_id` (PK), `customer_id` (FK → customers), `order_date`, `status`, `payment_method`
- **order_details** — `order_detail_id` (PK), `order_id` (FK → orders), `product_id` (FK → products), `quantity`, `unit_price`

```
categories 1───∞ products
                    │
                    ∞
customers 1───∞ orders 1───∞ order_details
```

Constraints enforced by the schema:

- `SERIAL` primary keys on all five tables.
- `NOT NULL` on mandatory columns (`customers`: customer_id, first_name, last_name, email; `categories`: category_id, category_name; `products`: product_id, product_name, category_id, price; `orders`: order_id, customer_id, order_date; `order_details`: order_detail_id, order_id, product_id, quantity, unit_price).
- `UNIQUE` on `customers.email`.
- `CHECK (... >= 0)` on `products.price`, `products.stock`, `order_details.quantity`, and `order_details.unit_price`.
- `price` and `unit_price` are stored as `DECIMAL(12,2)`.
- Four foreign keys: products.category_id → categories, orders.customer_id → customers, order_details.order_id → orders, order_details.product_id → products.

The **nullable** columns (which is where the intentional defects live) are `customers.city`, `customers.registration_date`, `products.stock`, `orders.status`, and `orders.payment_method`.

## Project structure

```
.
├── schema.sql               # Table definitions and constraints (PostgreSQL)
├── generate_data.py         # Deterministic sample-data generator
├── load_data.py             # Loads the CSVs into the AWS database (FK-safe order)
├── db/
│   └── connection.py        # Reads .env params and opens a psycopg2 connection
├── requirements.txt         # Python dependencies
├── .env.example             # Template for connection parameters (no real values)
├── data/                    # Generated CSV output (created by generate_data.py)
│   ├── categories.csv
│   ├── customers.csv
│   ├── products.csv
│   ├── orders.csv
│   └── order_details.csv
└── README.md
```

## Prerequisites & install

- Python 3.9+
- A PostgreSQL client (`psql`) if you want to apply the schema from the command line
- An AWS account with permission to create an Amazon RDS instance

Install the Python dependencies (pandas, psycopg2-binary, python-dotenv, hypothesis, pytest):

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## How to reproduce, end to end

### 1. Generate the sample data

Run the generator from the project root:

```bash
python generate_data.py
```

The generator uses a fixed seed (`random.Random(42)`) so output is byte-identical across runs. Its entry point is `generate(seed=42, output_dir="data", generation_date=None)`, which returns a `GenerationResult` carrying the generated `tables` and a `defect_summary`. On success it prints a line such as:

```
Generated N data-quality defects.
```

**Confirm the five CSVs were produced.** After the run, `data/` should contain exactly these five files with header rows:

```bash
ls -1 data/
# categories.csv
# customers.csv
# products.csv
# orders.csv
# order_details.csv
```

Row counts (excluding the header) should be 4 categories, 30 customers, 15 products, 100 orders, and 250 order_details. The generator overwrites any CSVs from a previous run and creates `data/` if it does not exist.

### 2. Provision the AWS database and connect

Provision a PostgreSQL instance on **Amazon RDS**:

- **Engine:** PostgreSQL (a current major version, e.g. PostgreSQL 15 or 16).
- **DB instance identifier:** choose a name (e.g. `ecommerce-test`). Record it — you'll reference it when locating the endpoint.
- **Publicly accessible:** set to **Yes** for this test so you can connect from your machine. (For anything beyond a throwaway test, prefer a private instance reached through a bastion/VPN.)
- **Security group inbound rule:** add a rule allowing **TCP on port 5432** (PostgreSQL) from your IP address (`My IP`), so your client can reach the instance.
- Wait until the instance reaches the **available** state before connecting.

Supply the connection parameters to the repository. The connection layer (`db/connection.py`) reads exactly five parameters — `REQUIRED_PARAMS = host, port, dbname, user, password` — from a `.env` file (via `load_config(env_path=".env")`), then `connect(config, timeout_seconds=10)` opens a psycopg2 connection with a 10-second timeout and verifies it can run a query.

Copy the template and fill in your RDS values:

```bash
cp .env.example .env
```

`.env` holds the five parameters:

```
host=your-instance.abc123.us-east-1.rds.amazonaws.com   # the RDS endpoint hostname
port=5432
dbname=ecommerce
user=your_db_user
password=your_db_password
```

**Credential storage.** `.env` is listed in `.gitignore` and must never be committed. Only `.env.example` (placeholders, no real values) is tracked. Parameters are referenced by name in code and configuration; secret values are never embedded in source or echoed in error messages.

### 3. Apply the schema

Apply `schema.sql` to the RDS instance. Using `psql` against the endpoint:

```bash
psql "host=$host port=$port dbname=$dbname user=$user" -f schema.sql
```

Or point any SQL client at the RDS endpoint and run the contents of `schema.sql`. Afterward the database should contain exactly the five tables and their four foreign key relationships.

### 4. Load the data

Load the generated CSVs into the hosted database:

```bash
python load_data.py --data-dir data --env .env
```

The loader (`load_data.py`) connects using the `.env` parameters and loads tables in a **foreign-key-safe order** — `LOAD_ORDER = categories, customers, products, orders, order_details` (parents before children). It:

- verifies all five CSVs exist before loading anything (reports the missing file otherwise);
- maps empty CSV cells in nullable columns to SQL `NULL` rather than empty strings;
- loads each file inside its own transaction, so a failure rolls back that file with no partial load;
- reports the offending table and row id on a foreign-key violation; and
- verifies each table's loaded row count matches its source CSV and reports any mismatch.

**Confirm the load.** On success the loader prints a per-table report and `Load complete.`. Expected counts are 4 / 30 / 15 / 100 / 250. You can double-check directly:

```sql
SELECT
  (SELECT count(*) FROM categories)    AS categories,
  (SELECT count(*) FROM customers)     AS customers,
  (SELECT count(*) FROM products)      AS products,
  (SELECT count(*) FROM orders)        AS orders,
  (SELECT count(*) FROM order_details) AS order_details;
```

## Intentional data-quality defects

The generator injects a small, bounded set of **intentional** defects so an analyst can practice detecting and cleaning realistic data-quality issues. These are expected, not bugs. Distinguish them from unintended errors by three characteristics:

1. **Where they live.** Defects are only ever placed in **nullable, non-key columns** — never in a primary key or foreign key. The only affected columns are:
   - `customers.city`
   - `orders.status`
   - `orders.payment_method`
   - `products.stock`
2. **What they look like.** Each defect is one of two types:
   - **`null`** — the cell is set to NULL (an empty cell in the CSV). Appears in any of the four columns above, including `products.stock`.
   - **`inconsistent`** — a mixed-case / whitespace-formatted variant of an otherwise valid value, so it represents the same logical value formatted badly. For example a city rendered as `bOgOtÁ`, or a status stored as `  ReTuRnEd ` (with surrounding whitespace). Only the string columns (`city`, `status`, `payment_method`) receive inconsistent values; `products.stock` (an integer) only ever receives `null` defects.
3. **How many.** At most `floor(10%)` of the rows in any single table carry a defect — up to 3 in customers, up to 10 in orders, up to 1 in products — with at least one defect placed overall, and at least one of each type (`null` and `inconsistent`) present.

Because defect placement is seeded, the same rows, columns, and values are affected on every run with the default seed. The generator also produces a machine-readable list of exactly what it altered: `GenerationResult.defect_summary` contains one `DefectRecord` per defect with its `table`, `column`, `row_id`, and `defect_type`. If a data anomaly falls outside these four columns and two types — for instance a NULL in a NOT NULL column, a broken foreign key, or a malformed price — treat it as an unintended error rather than an injected defect.

## Notes

- Prices are stored as `DECIMAL(12,2)` and represent Colombian pesos (COP); sample customers and cities are Colombian.
- `unit_price` on each `order_details` row is a snapshot copied from the product's `price` at generation time, so historical line items stay accurate even if a product's price changes later.
- The generator threads a single seeded RNG through every step, so the whole dataset — including defect locations — is reproducible.

## Analysis layer (EDA, metrics, and dashboard)

An `analysis/` package builds on the dataset. It reads from the RDS database
(via `db/connection.py`) and falls back to `data/*.csv` if the database is
unreachable. It normalizes the intentional data-quality defects (trims and
lowercases inconsistent `status` / `payment_method` values, keeps NULLs as
missing) before computing metrics. Revenue = `SUM(quantity * unit_price)`; AOV
and revenue metrics are computed over **completed** orders.

Files:

- `analysis/data_access.py` — load + clean the five tables (RDS or CSV).
- `analysis/metrics.py` — `average_order_value`, `revenue_per_customer`,
  `top_products` (top 5 by revenue or quantity), `revenue_per_month`.
- `analysis/eda.py` — prints shapes, dtypes, null counts, the defect summary,
  and the headline metrics.
- `analysis/dashboard.py` — a Dash app showing the monthly revenue trend, KPI
  cards (AOV, total revenue, completed orders), and the top-5-products table.

Install the extra dependencies (already in `requirements.txt`): `dash`,
`plotly`, `SQLAlchemy`.

### Run the EDA

```bash
python -m analysis.eda
```

### Run the dashboard

```bash
python -m analysis.dashboard
```

Then open http://127.0.0.1:8050 in a browser to see the revenue-per-month
trend.
