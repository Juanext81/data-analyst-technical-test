"""Data_Loader: load the five generated CSV files into the AWS_Database.

Design reference: design.md "4. Data_Loader (`load_data.py`)" and the
"Error Handling" table.

Behavioral contract (Requirement 9):
- ``load_all`` verifies that all five source CSVs exist *before* loading; a
  missing file is reported (by name) and no loading begins (AC 9.5).
- Tables are loaded in a foreign-key-safe order: parents before children
  (AC 9.2) via ``LOAD_ORDER``.
- Empty CSV cells for *nullable* columns are inserted as SQL ``NULL`` rather
  than empty strings (AC 9.3).
- Each file is loaded inside its own transaction. A mid-file failure rolls
  back that file's inserts entirely, so a target table is never left partially
  loaded (AC 9.4). On a foreign-key violation the violating table and the row
  identifier (the CSV row's primary-key value) are reported.
- After each file loads, the loaded row count in the table is compared with the
  data-row count of its source CSV and any mismatch is reported (AC 9.6).

All inserts are parameterized (values are never interpolated into SQL text) so
untrusted CSV content cannot alter the statement.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Load order and table metadata
# ---------------------------------------------------------------------------

# Foreign-key-safe order: categories and customers (parents) before products
# and orders, and those before order_details (AC 9.2). Loading in this order
# guarantees every child row's referenced parent already exists.
LOAD_ORDER: List[str] = ["categories", "customers", "products", "orders", "order_details"]

# The source CSV file name for each table lives in ``data_dir``.
CSV_FILENAMES: Dict[str, str] = {name: f"{name}.csv" for name in LOAD_ORDER}

# Canonical column order per table (matches schema.sql / the generator's CSV
# header). Used to build parameterized INSERT statements deterministically.
TABLE_COLUMNS: Dict[str, List[str]] = {
    "categories": ["category_id", "category_name"],
    "customers": [
        "customer_id",
        "first_name",
        "last_name",
        "email",
        "city",
        "registration_date",
    ],
    "products": [
        "product_id",
        "product_name",
        "category_id",
        "price",
        "stock",
    ],
    "orders": [
        "order_id",
        "customer_id",
        "order_date",
        "status",
        "payment_method",
    ],
    "order_details": [
        "order_detail_id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
    ],
}

# The primary-key column for each table -- used to report the row identifier on
# a foreign-key violation (AC 9.4).
PRIMARY_KEYS: Dict[str, str] = {
    "categories": "category_id",
    "customers": "customer_id",
    "products": "product_id",
    "orders": "order_id",
    "order_details": "order_detail_id",
}

# Nullable columns per table (from the design Data Models). An empty cell in one
# of these columns is loaded as SQL NULL (AC 9.3). Empty cells in any other
# column are passed through unchanged so the schema's NOT NULL constraints can
# reject genuinely malformed input.
NULLABLE_COLUMNS: Dict[str, frozenset] = {
    "categories": frozenset(),
    "customers": frozenset({"city"}),
    "products": frozenset({"stock"}),
    "orders": frozenset({"status", "payment_method"}),
    "order_details": frozenset(),
}


# ---------------------------------------------------------------------------
# Errors and report model
# ---------------------------------------------------------------------------


class LoadError(Exception):
    """Raised when loading cannot complete successfully.

    Used for a missing source CSV (AC 9.5), a foreign-key violation during load
    (AC 9.4), and a post-load row-count mismatch (AC 9.6). The message always
    identifies the offending file/table (and, for FK violations, the row id).
    """


@dataclass
class TableLoadResult:
    """Per-table outcome of a load."""

    table: str
    csv_row_count: int
    loaded_row_count: int


@dataclass
class LoadReport:
    """Summary of a completed load across all five tables."""

    results: List[TableLoadResult] = field(default_factory=list)

    @property
    def total_loaded(self) -> int:
        return sum(r.loaded_row_count for r in self.results)

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        lines = ["Load report:"]
        for r in self.results:
            lines.append(
                f"  {r.table}: {r.loaded_row_count} rows loaded "
                f"(source CSV data rows: {r.csv_row_count})"
            )
        lines.append(f"  total: {self.total_loaded} rows")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV reading / cell mapping
# ---------------------------------------------------------------------------


def _map_cell(table: str, column: str, value: Optional[str]):
    """Map a raw CSV cell to the value bound into the INSERT.

    An empty cell (``""`` or ``None``) in a nullable column becomes SQL
    ``NULL`` (Python ``None``) rather than an empty string (AC 9.3). Non-empty
    cells and cells in non-nullable columns are passed through unchanged.
    """
    if value is None:
        # A short row / missing field: treat as NULL only for nullable columns.
        return None if column in NULLABLE_COLUMNS[table] else value
    if value == "" and column in NULLABLE_COLUMNS[table]:
        return None
    return value


def _read_csv_rows(path: str, table: str) -> List[List]:
    """Read a CSV into a list of value-tuples in ``TABLE_COLUMNS`` order.

    The header row is consumed (and not counted as data). Each data row is
    projected onto the canonical column order and cell-mapped so empty nullable
    cells become ``None`` (AC 9.3).
    """
    columns = TABLE_COLUMNS[table]
    rows: List[List] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for record in reader:
            rows.append(
                [_map_cell(table, col, record.get(col)) for col in columns]
            )
    return rows


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _verify_files_exist(data_dir: str) -> None:
    """Verify all five source CSVs exist before any loading begins (AC 9.5).

    Raises:
        LoadError: naming the first missing file. No table is touched.
    """
    for table in LOAD_ORDER:
        path = os.path.join(data_dir, CSV_FILENAMES[table])
        if not os.path.isfile(path):
            raise LoadError(
                f"Missing source CSV for table '{table}': expected file "
                f"'{path}'. No tables were loaded."
            )


def _insert_sql(table: str) -> str:
    """Build a parameterized multi-column INSERT statement for ``table``.

    Values are supplied via placeholders (``%s``) so CSV content is bound as
    parameters and never interpolated into the SQL text.
    """
    columns = TABLE_COLUMNS[table]
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"


def _row_identifier(table: str, row: List):
    """Return the primary-key value from a projected CSV row for reporting."""
    pk = PRIMARY_KEYS[table]
    try:
        idx = TABLE_COLUMNS[table].index(pk)
    except ValueError:  # pragma: no cover - PKs are always in TABLE_COLUMNS
        return "<unknown>"
    return row[idx]


def _load_one(conn, table: str, data_dir: str) -> TableLoadResult:
    """Load a single table's CSV inside its own transaction.

    On any failure the transaction is rolled back so the target table is left
    unchanged (no partial load, AC 9.4). A foreign-key violation is reported
    with the violating table and the offending row's primary-key value.
    """
    # Import here so the module can be imported without psycopg2 installed
    # (e.g. for unit-testing the pure CSV/cell-mapping logic).
    from psycopg2 import errors as pg_errors

    path = os.path.join(data_dir, CSV_FILENAMES[table])
    rows = _read_csv_rows(path, table)
    sql = _insert_sql(table)

    cur = conn.cursor()
    current_row: Optional[List] = None
    try:
        for current_row in rows:
            cur.execute(sql, current_row)
        conn.commit()
    except pg_errors.ForeignKeyViolation as exc:
        conn.rollback()
        row_id = _row_identifier(table, current_row) if current_row else "<unknown>"
        raise LoadError(
            f"Foreign key violation while loading table '{table}' at row id "
            f"{row_id!r}; the file's transaction was rolled back "
            f"(no partial load)."
        ) from exc
    except Exception:
        # Any other failure also rolls back so no partial load remains.
        conn.rollback()
        raise
    finally:
        cur.close()

    # Verify loaded row count matches the CSV data-row count (AC 9.6).
    loaded = _count_rows(conn, table)
    if loaded != len(rows):
        raise LoadError(
            f"Row-count mismatch for table '{table}': loaded {loaded} rows but "
            f"source CSV has {len(rows)} data rows."
        )
    return TableLoadResult(
        table=table, csv_row_count=len(rows), loaded_row_count=loaded
    )


def _count_rows(conn, table: str) -> int:
    """Return the number of rows currently in ``table``."""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        (count,) = cur.fetchone()
        return int(count)
    finally:
        cur.close()


def load_all(conn, data_dir: str = "data") -> LoadReport:
    """Load all five CSVs into the AWS_Database and confirm completion.

    Verifies that all five CSVs exist (AC 9.5), loads them in FK-safe order
    (AC 9.2), maps empty nullable cells to SQL ``NULL`` (AC 9.3), and verifies
    per-table row counts against the source CSVs (AC 9.6). Each file loads in
    its own transaction; on a foreign-key violation the offending table + row
    id are reported and that file's transaction is rolled back (AC 9.4).

    Args:
        conn: An already-open psycopg2 connection (kept as a parameter so the
            loader is testable without owning connection setup).
        data_dir: Directory containing the five source CSVs (default "data").

    Returns:
        LoadReport: per-table row counts once all rows are loaded (AC 9.1).

    Raises:
        LoadError: on a missing source CSV, a foreign-key violation, or a
            post-load row-count mismatch. The message identifies the offending
            file/table (and row id for FK violations).
    """
    # AC 9.5: verify everything is present before touching any table.
    _verify_files_exist(data_dir)

    report = LoadReport()
    for table in LOAD_ORDER:  # AC 9.2: parents before children.
        report.results.append(_load_one(conn, table, data_dir))
    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main(argv: Optional[List[str]] = None) -> int:
    """CLI: connect using db.connection and run ``load_all``.

    Uses ``load_config``/``connect`` from the connection layer to obtain a live
    connection, runs the load, prints the report, and closes the connection.
    """
    import argparse

    from db.connection import connect, load_config

    parser = argparse.ArgumentParser(
        description="Load generated CSVs into the AWS PostgreSQL database."
    )
    parser.add_argument(
        "--data-dir", default="data", help="Directory containing the CSVs."
    )
    parser.add_argument(
        "--env", default=".env", help="Path to the .env file with credentials."
    )
    args = parser.parse_args(argv)

    config = load_config(args.env)
    conn = connect(config)
    try:
        report = load_all(conn, data_dir=args.data_dir)
    finally:
        conn.close()

    print(report)
    print("Load complete.")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI wiring
    raise SystemExit(_main())
