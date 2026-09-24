"""E-commerce sample data generator (Dataset_Generator).

Deterministic generator that builds a fully valid, referentially consistent
e-commerce dataset, injects a bounded number of intentional data-quality
defects into nullable non-key columns, validates referential integrity, and
exports the result as five CSV files under ``data/``.

Determinism (Requirement 2.7): every random draw flows from a single seeded
``random.Random`` instance created in :func:`generate`, so ordering is stable
and repeated runs with the same seed produce byte-identical output.

This module currently provides the entry point, supporting data models, and
the ``GenerationError`` exception. The individual builders, defect injection,
referential-integrity validation, and CSV export are implemented in later
tasks; their calls below are intentional stubs.
"""

from __future__ import annotations

import csv
import os
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Fixed generation parameters (see Requirement 2 volumes)
# ---------------------------------------------------------------------------

DEFAULT_SEED = 42

NUM_CUSTOMERS = 30
NUM_CATEGORIES = 4
NUM_PRODUCTS = 15
NUM_ORDERS = 100
NUM_ORDER_DETAILS = 250

# The five tables, in foreign-key-safe order (parents before children). Used
# by CSV export and downstream loading.
TABLE_NAMES = ["categories", "customers", "products", "orders", "order_details"]

# Canonical column order per table (matches schema.sql column order). Used as
# the CSV header row (Requirement 6.3) so output is deterministic and
# independent of dict iteration order.
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

# ---------------------------------------------------------------------------
# Reference data (preserved from the project's domain: Colombian e-commerce).
# These seed the deterministic builders implemented in later tasks.
# ---------------------------------------------------------------------------

# Exactly 4 categories (Requirement 2.2).
CATEGORY_NAMES = ["Electronics", "Home", "Sports", "Accessories"]

# Sample Colombian first/last names and cities for customer generation.
FIRST_NAMES = [
    "Santiago", "Valentina", "Mateo", "Isabella", "Sebastián", "Camila",
    "Nicolás", "Salomé", "Samuel", "Mariana", "Alejandro", "Sofía",
    "Andrés", "Daniela", "Juan", "Laura", "Felipe", "Gabriela",
    "David", "Manuela", "Diego", "Antonella", "Tomás", "Luciana",
    "Emiliano", "Sara", "Martín", "Valeria", "Simón", "Emma",
]

LAST_NAMES = [
    "Rodríguez", "Gómez", "González", "Martínez", "López", "Hernández",
    "Ramírez", "Torres", "Flórez", "Vargas", "Castro", "Ruiz",
    "Díaz", "Moreno", "Rojas", "Muñoz", "Suárez", "Jiménez",
    "Cárdenas", "Ortiz", "Gutiérrez", "Álvarez", "Mendoza", "Restrepo",
]

CITIES = [
    "Bogotá", "Medellín", "Cali", "Barranquilla", "Cartagena",
    "Bucaramanga", "Pereira", "Manizales", "Santa Marta", "Cúcuta",
]

# Product name fragments per category, used to build the 15 products so that
# each of the 4 categories receives at least one product (Requirement 2.3, 2.6).
PRODUCT_NAMES_BY_CATEGORY: Dict[str, List[str]] = {
    "Electronics": [
        "Smartphone", "Laptop", "Wireless Headphones", "Bluetooth Speaker",
        "Smartwatch", "Tablet",
    ],
    "Home": [
        "Coffee Maker", "Air Fryer", "Vacuum Cleaner", "Table Lamp",
    ],
    "Sports": [
        "Running Shoes", "Yoga Mat", "Dumbbell Set", "Bicycle Helmet",
    ],
    "Accessories": [
        "Leather Wallet", "Sunglasses", "Backpack", "Phone Case",
    ],
}

# Value pools for nullable order columns.
ORDER_STATUSES = ["completed", "pending", "shipped", "cancelled", "returned"]
PAYMENT_METHODS = ["credit_card", "debit_card", "cash", "bank_transfer", "pse"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GenerationError(Exception):
    """Raised when the dataset cannot be generated as a valid, consistent whole.

    Examples include a generated foreign key value with no parent record
    (Requirement 2.8), an order_detail referencing a product that cannot be
    resolved or has no price (Requirement 5.2), or a failure to write one of
    the CSV files (Requirement 6.6). Raising this before any file is written
    guarantees a failed run produces zero output.
    """


# ---------------------------------------------------------------------------
# Supporting in-memory data models (see design "Data Models")
# ---------------------------------------------------------------------------


@dataclass
class DefectRecord:
    """A single intentional data-quality defect that was injected.

    Attributes:
        table: The table containing the affected row (e.g. ``"customers"``).
        column: The nullable non-key column that was altered.
        row_id: The primary key of the affected row.
        defect_type: ``"null"`` for a NULL value or ``"inconsistent"`` for a
            value deviating in format, unit, or casing.
    """

    table: str
    column: str
    row_id: int
    defect_type: str


@dataclass
class DefectSummary:
    """Summary of every intentional data-quality defect injected in a run.

    The set of records here SHALL exactly describe the cells actually altered
    by defect injection (Requirement 4.6).
    """

    records: List[DefectRecord] = field(default_factory=list)


@dataclass
class GenerationResult:
    """The outcome of a successful generation run.

    Attributes:
        tables: Mapping of table name to its generated rows. Each table is a
            list of row dicts keyed by column name (parent-before-child order
            is preserved by :data:`TABLE_NAMES`).
        defect_summary: The summary of injected data-quality defects.
    """

    tables: Dict[str, List[Dict[str, Any]]]
    defect_summary: DefectSummary


# ---------------------------------------------------------------------------
# Deterministic table builders
# ---------------------------------------------------------------------------

# Window length for registration/order dates (Requirement 2.9, 3.1): the
# inclusive 365-day span preceding the generation date.
DATE_WINDOW_DAYS = 365


def build_categories(rng: random.Random) -> List[Dict[str, Any]]:
    """Build exactly 4 category rows with unique ids (Requirement 2.2).

    Produces one row per name in :data:`CATEGORY_NAMES` with a 1-based
    ``category_id``. The ``rng`` argument is accepted for interface
    consistency with the other builders; category construction is fully
    determined by :data:`CATEGORY_NAMES` and needs no random draws, keeping
    output stable regardless of RNG state.

    Args:
        rng: The single seeded RNG threaded through generation. Unused here
            but kept in the signature so callers pass it uniformly.

    Returns:
        A list of 4 dicts, each keyed by ``category_id`` and ``category_name``.
    """
    return [
        {"category_id": index, "category_name": name}
        for index, name in enumerate(CATEGORY_NAMES, start=1)
    ]


def build_customers(
    rng: random.Random, generation_date: date
) -> List[Dict[str, Any]]:
    """Build exactly 30 customer rows with unique ids and emails (Requirement 2.1).

    Each customer receives a 1-based ``customer_id``, a first/last name drawn
    from the reference pools, a city, and a ``registration_date`` that falls
    within the inclusive window [``generation_date`` − 365 days,
    ``generation_date``] (Requirements 3.1, 2.9). Emails are derived from the
    customer name and id so they are guaranteed unique across the 30 rows.

    All random draws flow from ``rng`` so that, for a fixed seed, the rows and
    their order are byte-stable across runs (Requirement 2.7).

    Args:
        rng: The single seeded RNG threaded through generation.
        generation_date: The reference "now" that anchors the date window.

    Returns:
        A list of 30 dicts keyed by ``customer_id``, ``first_name``,
        ``last_name``, ``email``, ``city``, and ``registration_date``.
    """
    customers: List[Dict[str, Any]] = []
    for customer_id in range(1, NUM_CUSTOMERS + 1):
        first_name = rng.choice(FIRST_NAMES)
        last_name = rng.choice(LAST_NAMES)
        city = rng.choice(CITIES)

        # A random offset in [0, 365] days before the generation date yields a
        # registration_date within the inclusive window (Requirements 3.1, 2.9).
        days_ago = rng.randint(0, DATE_WINDOW_DAYS)
        registration_date = generation_date - timedelta(days=days_ago)

        # Derive a unique email from name plus the unique customer_id. Strip
        # accents/non-ascii so the local part is a clean email token while the
        # id suffix guarantees uniqueness even for repeated name pairs.
        local_part = _email_local_part(first_name, last_name, customer_id)
        email = f"{local_part}@example.com"

        customers.append(
            {
                "customer_id": customer_id,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "city": city,
                "registration_date": registration_date,
            }
        )
    return customers


def _email_local_part(first_name: str, last_name: str, customer_id: int) -> str:
    """Build a clean, unique email local part from a name and customer id.

    Lowercases the name, transliterates common Spanish accents to ASCII, and
    drops any remaining non-alphanumeric characters, then appends the unique
    ``customer_id`` so no two customers can collide even with duplicate names.
    """
    raw = f"{first_name}.{last_name}".lower()
    transliterated = raw.translate(_ACCENT_MAP)
    cleaned = "".join(ch for ch in transliterated if ch.isalnum() or ch == ".")
    return f"{cleaned}{customer_id}"


# Map accented characters used in the reference names to ASCII equivalents so
# derived emails stay in a conventional format.
_ACCENT_MAP = {
    ord("á"): "a",
    ord("é"): "e",
    ord("í"): "i",
    ord("ó"): "o",
    ord("ú"): "u",
    ord("ñ"): "n",
    ord("ü"): "u",
}


# Price bounds (in COP) for randomly assigned product prices. Kept comfortably
# within the DECIMAL(12,2) domain (0.00 .. 9,999,999,999.99) required by the
# schema, and always non-negative (Requirement 1.11, 1.12).
MIN_PRICE_COP = 5_000
MAX_PRICE_COP = 4_000_000

# Bounds for the (nullable) stock column. A valid, non-negative integer is
# built here; defect injection may later NULL/perturb it (Requirement 4.x).
MIN_STOCK = 0
MAX_STOCK = 500


def build_products(
    rng: random.Random, categories: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Build exactly 15 product rows spread across all 4 categories.

    Guarantees (Requirements 2.3, 2.6):
      * Exactly :data:`NUM_PRODUCTS` (15) rows are produced.
      * Every category in ``categories`` is assigned at least one product, so
        no category is left empty.
      * Each product belongs to exactly one category via a ``category_id`` that
        is a valid foreign key into the passed-in ``categories`` list.

    The first ``len(categories)`` products are assigned round-robin, one per
    category, to satisfy the "at least one product per category" guarantee.
    The remaining products are assigned to categories chosen at random from
    ``categories`` using ``rng``. Product names are drawn (without collision
    within a category, falling back to a numbered suffix when a category's name
    pool is exhausted) from :data:`PRODUCT_NAMES_BY_CATEGORY`. Prices and stock
    are drawn from ``rng`` as well, so for a fixed seed the rows and their order
    are byte-stable across runs (Requirement 2.7).

    Args:
        rng: The single seeded RNG threaded through generation.
        categories: The category rows produced by :func:`build_categories`;
            each must expose ``category_id`` and ``category_name``.

    Returns:
        A list of 15 dicts keyed by ``product_id``, ``product_name``,
        ``category_id``, ``price``, and ``stock``.
    """
    # Map category_id -> category_name so we can pick names from the correct
    # pool for whichever category a product is assigned to.
    name_by_category_id = {
        category["category_id"]: category["category_name"]
        for category in categories
    }
    category_ids = [category["category_id"] for category in categories]

    # Build the sequence of category ids, one per product. Seed the sequence
    # with one slot per category (coverage guarantee), then fill the rest with
    # random category ids so totals reach NUM_PRODUCTS.
    assigned_category_ids: List[int] = list(category_ids)
    remaining = NUM_PRODUCTS - len(assigned_category_ids)
    for _ in range(remaining):
        assigned_category_ids.append(rng.choice(category_ids))

    # Track used names per category to keep product names unique within a
    # category while still drawing from the reference pools.
    used_names_by_category: Dict[int, set] = {cid: set() for cid in category_ids}

    products: List[Dict[str, Any]] = []
    for product_id, category_id in enumerate(assigned_category_ids, start=1):
        category_name = name_by_category_id[category_id]
        product_name = _pick_product_name(
            rng, category_name, used_names_by_category[category_id]
        )

        # Non-negative price within the DECIMAL(12,2) domain, quantized to
        # exactly 2 decimal places.
        price = round(rng.uniform(MIN_PRICE_COP, MAX_PRICE_COP), 2)
        stock = rng.randint(MIN_STOCK, MAX_STOCK)

        products.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "category_id": category_id,
                "price": price,
                "stock": stock,
            }
        )
    return products


def _pick_product_name(
    rng: random.Random, category_name: str, used_names: set
) -> str:
    """Pick a product name for ``category_name`` unused within that category.

    Draws from :data:`PRODUCT_NAMES_BY_CATEGORY` for the category, avoiding
    names already used in that category. If the category's name pool is
    exhausted (more products than distinct names), a numbered suffix keeps the
    name unique within the category.
    """
    pool = PRODUCT_NAMES_BY_CATEGORY.get(category_name, [])
    available = [name for name in pool if name not in used_names]
    if available:
        name = rng.choice(available)
        used_names.add(name)
        return name

    # Pool exhausted: derive a unique, deterministic fallback name.
    base = rng.choice(pool) if pool else category_name
    suffix = 2
    candidate = f"{base} {suffix}"
    while candidate in used_names:
        suffix += 1
        candidate = f"{base} {suffix}"
    used_names.add(candidate)
    return candidate


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

# Distribution parameters for the 12-month order window (Requirement 3.3).
NUM_MONTHS = 12
# Per-month cap: no single calendar month may hold more than 40% of all orders.
MAX_ORDERS_PER_MONTH = int(NUM_ORDERS * 0.40)  # floor(0.40 * 100) = 40


def _month_windows(
    generation_date: date,
) -> List[Dict[str, date]]:
    """Compute the 12 calendar-month windows spanning the 365-day date range.

    The order window is the inclusive span [generation_date - 365 days,
    generation_date] (Requirements 2.9, 3.2). This function splits that span
    into the 12 calendar months it touches, ordered oldest-first, each clamped
    to the window boundaries so that no returned day ever falls outside the
    inclusive range.

    Args:
        generation_date: The reference "now" anchoring the window.

    Returns:
        A list of exactly 12 dicts, each with ``start`` and ``end`` dates
        (inclusive) marking the valid day range for that calendar month within
        the window, ordered from oldest month to the generation month.
    """
    window_start = generation_date - timedelta(days=DATE_WINDOW_DAYS)

    # Build the 12 calendar months ending in the generation month. Walk back
    # from the generation month one month at a time to collect 12 (year, month)
    # pairs, then order them oldest-first.
    months: List[tuple] = []
    year, month = generation_date.year, generation_date.month
    for _ in range(NUM_MONTHS):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()

    windows: List[Dict[str, date]] = []
    for year, month in months:
        first_day = date(year, month, 1)
        # Last day of this calendar month.
        if month == 12:
            next_first = date(year + 1, 1, 1)
        else:
            next_first = date(year, month + 1, 1)
        last_day = next_first - timedelta(days=1)

        # Clamp to the inclusive window so no day escapes [window_start,
        # generation_date].
        start = max(first_day, window_start)
        end = min(last_day, generation_date)
        windows.append({"start": start, "end": end})
    return windows


def _allocate_orders_per_month() -> List[int]:
    """Allocate the 100 orders across the 12 months honoring the bounds.

    Guarantees (Requirement 3.3):
      * Every one of the 12 months receives at least 1 order.
      * No month exceeds :data:`MAX_ORDERS_PER_MONTH` (40).
      * The counts sum to exactly :data:`NUM_ORDERS` (100).

    The allocation is fully deterministic (no RNG): seed each month with 1
    order, then fill remaining orders left-to-right up to the per-month cap.
    Keeping this deterministic and RNG-free means the per-month *counts* are
    stable regardless of RNG state; the RNG only affects which customer and
    which concrete day each order gets.

    Returns:
        A list of 12 ints (oldest month first) summing to 100.
    """
    counts = [1] * NUM_MONTHS
    remaining = NUM_ORDERS - NUM_MONTHS
    index = 0
    while remaining > 0:
        if counts[index] < MAX_ORDERS_PER_MONTH:
            counts[index] += 1
            remaining -= 1
        index = (index + 1) % NUM_MONTHS
    return counts


def build_orders(
    rng: random.Random,
    customers: List[Dict[str, Any]],
    generation_date: date,
) -> List[Dict[str, Any]]:
    """Build exactly 100 order rows distributed across the 12-month window.

    Guarantees (Requirements 2.4, 2.9, 3.2, 3.3, 3.4, 3.5):
      * Exactly :data:`NUM_ORDERS` (100) rows are produced.
      * Each order references an existing customer via ``customer_id``.
      * Every one of the 12 calendar months in the window contains at least one
        order and no month contains more than :data:`MAX_ORDERS_PER_MONTH` (40).
      * Every ``order_date`` falls within the inclusive window
        [``generation_date`` - 365 days, ``generation_date``].
      * Every ``order_date`` is on or after the referenced customer's
        ``registration_date`` and on or before ``generation_date``.

    Algorithm:
      1. Split the window into 12 calendar-month day-ranges (oldest first).
      2. Deterministically allocate order counts per month (≥1 each, ≤40, sum
         100).
      3. For each order slot in a month, pick a customer at random; if that
         customer registered too late to have a valid day in the month (i.e.
         ``registration_date`` > the month's clamped end), re-pair with a
         customer whose registration allows a valid date in that month
         (Requirement 3.5, late-registrant edge case). Then draw a concrete day
         in [max(month_start, registration_date), month_end].

    All random draws flow from ``rng`` so that, for a fixed seed, the rows and
    their order are byte-stable across runs (Requirement 2.7).

    Args:
        rng: The single seeded RNG threaded through generation.
        customers: The customer rows produced by :func:`build_customers`; each
            must expose ``customer_id`` and ``registration_date``.
        generation_date: The reference "now" anchoring the date window.

    Returns:
        A list of 100 dicts keyed by ``order_id``, ``customer_id``,
        ``order_date``, ``status``, and ``payment_method``.

    Raises:
        GenerationError: If no customer can be paired with a given month (i.e.
            every customer registered after the month's valid range ends). With
            the standard 365-day window and 30 customers this cannot happen,
            but it is reported rather than silently producing an out-of-window
            date.
    """
    windows = _month_windows(generation_date)
    per_month_counts = _allocate_orders_per_month()

    orders: List[Dict[str, Any]] = []
    order_id = 1
    for month_window, count in zip(windows, per_month_counts):
        month_start = month_window["start"]
        month_end = month_window["end"]

        # Customers eligible for this month are those registered on or before
        # the month's clamped end day; only they can receive a valid order date
        # within this month (Requirements 3.4, 3.5).
        eligible = [
            customer
            for customer in customers
            if customer["registration_date"] <= month_end
        ]
        if not eligible:
            raise GenerationError(
                "No customer can be assigned an order in the month ending "
                f"{month_end.isoformat()}: every customer registered later."
            )

        for _ in range(count):
            # Pick any customer; re-pair with an eligible one if the initial
            # random pick registered too late for this month (Requirement 3.5).
            customer = rng.choice(customers)
            if customer["registration_date"] > month_end:
                customer = rng.choice(eligible)

            # The earliest valid day is the later of the month start and the
            # customer's registration date; the latest is the month end (which
            # is already clamped to <= generation_date).
            earliest = max(month_start, customer["registration_date"])
            latest = month_end
            span_days = (latest - earliest).days
            order_date = earliest + timedelta(days=rng.randint(0, span_days))

            orders.append(
                {
                    "order_id": order_id,
                    "customer_id": customer["customer_id"],
                    "order_date": order_date,
                    "status": rng.choice(ORDER_STATUSES),
                    "payment_method": rng.choice(PAYMENT_METHODS),
                }
            )
            order_id += 1

    return orders


# ---------------------------------------------------------------------------
# Order details
# ---------------------------------------------------------------------------

# Bounds for the (non-nullable) quantity column. A small, realistic per-line
# quantity keeps aggregate revenue meaningful while staying strictly positive
# and well within the CHECK (quantity >= 0) domain.
MIN_QUANTITY = 1
MAX_QUANTITY = 5


def build_order_details(
    rng: random.Random,
    orders: List[Dict[str, Any]],
    products: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build exactly 250 order_detail rows with snapshotted unit prices.

    Guarantees (Requirements 2.5, 5.1, 5.3):
      * Exactly :data:`NUM_ORDER_DETAILS` (250) rows are produced.
      * Each row references an existing order via ``order_id`` and an existing
        product via ``product_id`` (valid foreign keys, Requirement 2.5).
      * ``unit_price`` is set to a *copy* of the referenced product's ``price``
        at generation time, quantized to exactly 2 decimal places
        (Requirement 5.1). The value is copied by value (via ``round``), never
        held as a reference to the product row, so a later change to the
        product's ``price`` cannot mutate an already-generated line item
        (Requirement 5.3, snapshot immutability).

    Line items are distributed across orders so that every order receives at
    least one line item before the remaining slots are filled: the first
    ``len(orders)`` details are assigned round-robin, one per order, and any
    remaining slots pick an order at random. Each line's product is chosen at
    random from ``products``. Quantity is drawn from ``rng`` in
    [:data:`MIN_QUANTITY`, :data:`MAX_QUANTITY`].

    All random draws flow from ``rng`` so that, for a fixed seed, the rows and
    their order are byte-stable across runs (Requirement 2.7).

    Args:
        rng: The single seeded RNG threaded through generation.
        orders: The order rows produced by :func:`build_orders`; each must
            expose ``order_id``.
        products: The product rows produced by :func:`build_products`; each
            must expose ``product_id`` and ``price``.

    Returns:
        A list of 250 dicts keyed by ``order_detail_id``, ``order_id``,
        ``product_id``, ``quantity``, and ``unit_price``.

    Raises:
        GenerationError: If ``orders`` or ``products`` is empty, since no valid
            foreign key could then be assigned to a line item.
    """
    if not orders:
        raise GenerationError(
            "Cannot build order_details: no orders exist to reference."
        )
    if not products:
        raise GenerationError(
            "Cannot build order_details: no products exist to reference."
        )

    order_ids = [order["order_id"] for order in orders]

    # Seed one line item per order (so no order is left empty), then fill the
    # remaining slots with randomly chosen orders until we reach 250.
    assigned_order_ids: List[int] = list(order_ids[:NUM_ORDER_DETAILS])
    remaining = NUM_ORDER_DETAILS - len(assigned_order_ids)
    for _ in range(remaining):
        assigned_order_ids.append(rng.choice(order_ids))

    order_details: List[Dict[str, Any]] = []
    for order_detail_id, order_id in enumerate(assigned_order_ids, start=1):
        product = rng.choice(products)
        quantity = rng.randint(MIN_QUANTITY, MAX_QUANTITY)

        # Snapshot the price BY VALUE. round() produces a fresh float quantized
        # to 2 decimals, so the stored unit_price is independent of the product
        # row and any later mutation of product["price"] (Requirement 5.3).
        unit_price = round(product["price"], 2)

        order_details.append(
            {
                "order_detail_id": order_detail_id,
                "order_id": order_id,
                "product_id": product["product_id"],
                "quantity": quantity,
                "unit_price": unit_price,
            }
        )
    return order_details


# ---------------------------------------------------------------------------
# Referential-integrity validation
# ---------------------------------------------------------------------------


def validate_referential_integrity(tables: Dict[str, List[Dict[str, Any]]]) -> None:
    """Validate every foreign key in the dataset before any file is written.

    Runs entirely in memory over the in-memory ``tables`` so that a failure
    produces zero output (Requirement 2.8): callers invoke this *before* CSV
    export, and any dangling reference aborts generation by raising
    :class:`GenerationError` with no side effects.

    The foreign keys checked (design "Data Models") are:

      * ``products.category_id``     -> ``categories.category_id``
      * ``orders.customer_id``       -> ``customers.customer_id``
      * ``order_details.order_id``   -> ``orders.order_id``
      * ``order_details.product_id`` -> ``products.product_id``

    On the first dangling foreign key, a :class:`GenerationError` is raised
    naming the offending table, column, the affected row's primary key, and the
    missing parent value (Requirement 2.8).

    Additionally, for ``order_details`` the referenced product must be
    resolvable *and* carry a usable ``price`` (not ``None`` and not missing). A
    line item whose product cannot be resolved or has no price is rejected and
    a :class:`GenerationError` is raised identifying the unresolved product
    (Requirement 5.2). Because this function performs no mutation and raises on
    the first offending row, prior (valid) rows are left unchanged.

    Args:
        tables: Mapping of table name to its rows (list of column-keyed dicts),
            keyed by the five names in :data:`TABLE_NAMES`.

    Returns:
        ``None``. The function is a pure validator: it either returns quietly
        when every reference resolves or raises :class:`GenerationError`.

    Raises:
        GenerationError: If any foreign key value has no parent row, or if an
            ``order_details`` row references a product that cannot be resolved
            or has no price.
    """
    categories = tables.get("categories", [])
    customers = tables.get("customers", [])
    products = tables.get("products", [])
    orders = tables.get("orders", [])
    order_details = tables.get("order_details", [])

    # Build parent primary-key lookups once. Products map to their full row so
    # the order_details price check can inspect the referenced product.
    category_ids = {row["category_id"] for row in categories}
    customer_ids = {row["customer_id"] for row in customers}
    order_ids = {row["order_id"] for row in orders}
    products_by_id = {row["product_id"]: row for row in products}

    # products.category_id -> categories.category_id
    for product in products:
        category_id = product.get("category_id")
        if category_id not in category_ids:
            raise GenerationError(
                "Referential integrity violation: products.category_id="
                f"{category_id!r} (product_id={product.get('product_id')!r}) "
                "has no matching categories.category_id."
            )

    # orders.customer_id -> customers.customer_id
    for order in orders:
        customer_id = order.get("customer_id")
        if customer_id not in customer_ids:
            raise GenerationError(
                "Referential integrity violation: orders.customer_id="
                f"{customer_id!r} (order_id={order.get('order_id')!r}) "
                "has no matching customers.customer_id."
            )

    # order_details.order_id -> orders.order_id, and
    # order_details.product_id -> products.product_id (which must have a price).
    for detail in order_details:
        detail_id = detail.get("order_detail_id")

        order_id = detail.get("order_id")
        if order_id not in order_ids:
            raise GenerationError(
                "Referential integrity violation: order_details.order_id="
                f"{order_id!r} (order_detail_id={detail_id!r}) "
                "has no matching orders.order_id."
            )

        product_id = detail.get("product_id")
        product = products_by_id.get(product_id)
        if product is None:
            # Unresolvable product: reject this line item (Requirement 5.2).
            raise GenerationError(
                "Unresolved product in order_details: product_id="
                f"{product_id!r} (order_detail_id={detail_id!r}) "
                "has no matching products.product_id."
            )

        # A resolvable product with no usable price cannot supply a unit_price
        # snapshot; reject the line item identifying the product (Req 5.2).
        if product.get("price") is None:
            raise GenerationError(
                "Unresolved product price in order_details: product_id="
                f"{product_id!r} (order_detail_id={detail_id!r}) "
                "references products.price that is missing or NULL."
            )


# ---------------------------------------------------------------------------
# Intentional data-quality defect injection
# ---------------------------------------------------------------------------

# The only columns eligible for defects: nullable, non-key columns (never a
# primary key or foreign key), per the design "Defect model" and Requirement
# 4.5. Each entry is (table, column). ``products.stock`` is an INT column with
# a CHECK (stock >= 0) constraint, so it only ever receives ``null`` defects;
# the string columns carry the ``inconsistent`` (format/unit/casing) defects,
# which still load into their VARCHAR columns.
DEFECT_TARGETS: List[tuple] = [
    ("customers", "city"),
    ("orders", "status"),
    ("orders", "payment_method"),
    ("products", "stock"),
]

# Primary key of each defect-eligible table, used to record the affected row
# id in a DefectRecord (Requirement 4.6).
_PRIMARY_KEY_BY_TABLE: Dict[str, str] = {
    "customers": "customer_id",
    "orders": "order_id",
    "products": "product_id",
}

# Fraction of a table's rows that may carry defects, rounded down, per table
# (Requirement 4.4).
DEFECT_RATE = 0.10


def _make_inconsistent_value(rng: random.Random, table: str, column: str,
                             original: Any) -> Any:
    """Derive an inconsistent (format/unit/casing) variant of ``original``.

    Produces a value that deviates from the expected format, unit, or casing of
    the other values in the same column (Requirement 4.3) while remaining a
    string that still loads into the column's VARCHAR type. For example a city
    ``"Bogotá"`` becomes a mixed-case ``"bOgOtÁ"``; a status/payment value gets
    surrounding whitespace and randomized casing so it reads as the same
    logical value formatted inconsistently.

    The transformation flows entirely from ``rng`` so a fixed seed yields the
    same inconsistent value across runs (Requirement 4.7).
    """
    text = "" if original is None else str(original)

    # Alternate the casing of each character, starting from a seed-dependent
    # offset, to produce a jarring mixed-case rendering distinct from the clean
    # source values.
    offset = rng.randint(0, 1)
    scrambled = "".join(
        ch.upper() if (index + offset) % 2 == 0 else ch.lower()
        for index, ch in enumerate(text)
    )

    # For the short enumerated string columns, also introduce a formatting
    # deviation (surrounding whitespace) so the value differs in *format* too,
    # not only casing. City values rely on the casing deviation alone to stay a
    # plausible (if malformed) place name.
    if column in ("status", "payment_method"):
        return f"  {scrambled} "
    return scrambled


def inject_defects(
    rng: random.Random, tables: Dict[str, List[Dict[str, Any]]]
) -> DefectSummary:
    """Inject bounded data-quality defects into nullable non-key columns.

    Mutates ``tables`` in place, replacing a bounded number of cells in the
    eligible nullable, non-key columns (:data:`DEFECT_TARGETS`) with either a
    NULL (``None``) or an inconsistent value, and returns a
    :class:`DefectSummary` describing exactly the cells that were altered.

    Guarantees (Requirement 4):
      * Only nullable non-key columns are touched — never a primary key or
        foreign key column (4.5). Eligible columns are ``customers.city``,
        ``orders.status``, ``orders.payment_method``, and ``products.stock``.
      * At least one ``null`` defect and at least one ``inconsistent`` defect
        are introduced (4.2, 4.3).
      * At most ``floor(0.10 * row_count)`` defects are placed in any single
        table, and at least one defect is placed overall (4.1, 4.4).
      * Each altered cell is recorded once in the returned summary as a
        :class:`DefectRecord` with its table, column, affected row's primary
        key, and defect type; the summary exactly matches the cells actually
        altered (4.6).
      * ``products.stock`` (an INT with a non-negative CHECK) only receives
        ``null`` defects; inconsistent values are confined to the VARCHAR
        string columns so every defect still loads.

    All choices — which rows, which columns, and each concrete inconsistent
    value — flow from the passed-in ``rng``, so for a fixed seed the defect
    columns, rows, and values are identical across runs (Requirement 4.7).

    Args:
        rng: The single seeded RNG threaded through generation.
        tables: Mapping of table name to its rows (list of column-keyed dicts).
            The eligible tables (``customers``, ``orders``, ``products``) must
            be present; each row must expose that table's primary key.

    Returns:
        A :class:`DefectSummary` listing every injected defect. Its records
        correspond one-to-one with the cells mutated in ``tables``.
    """
    summary = DefectSummary()

    # Compute the per-table cap once: floor(0.10 * row_count) for every table
    # that owns at least one eligible column (Requirement 4.4).
    eligible_tables = {table for table, _ in DEFECT_TARGETS}
    per_table_cap: Dict[str, int] = {}
    for table in eligible_tables:
        row_count = len(tables.get(table, []))
        per_table_cap[table] = int(row_count * DEFECT_RATE)  # floor

    # Track how many defects each table has received so we never exceed its
    # cap, and remember which (table, row_id, column) cells were already hit so
    # a single cell is never defected twice.
    defects_per_table: Dict[str, int] = {table: 0 for table in eligible_tables}
    used_cells: set = set()

    def _rows_for(table: str) -> List[Dict[str, Any]]:
        return tables.get(table, [])

    def _try_place(table: str, column: str, defect_type: str) -> bool:
        """Attempt to place one defect of ``defect_type`` in ``table.column``.

        Picks an as-yet-undefected row for the column, applies the mutation,
        records it, and respects the table's cap. Returns True if a defect was
        placed, False if the table is at its cap or has no eligible row left.
        """
        if defects_per_table[table] >= per_table_cap.get(table, 0):
            return False

        pk = _PRIMARY_KEY_BY_TABLE[table]
        rows = _rows_for(table)
        # Candidate rows: those whose (table, row_id, column) cell is untouched.
        candidates = [
            row for row in rows
            if (table, row[pk], column) not in used_cells
        ]
        if not candidates:
            return False

        row = rng.choice(candidates)
        row_id = row[pk]

        if defect_type == "null":
            row[column] = None
        else:  # "inconsistent"
            row[column] = _make_inconsistent_value(
                rng, table, column, row[column]
            )

        used_cells.add((table, row_id, column))
        defects_per_table[table] += 1
        summary.records.append(
            DefectRecord(
                table=table,
                column=column,
                row_id=row_id,
                defect_type=defect_type,
            )
        )
        return True

    # --- Mandatory defects (Requirements 4.1, 4.2, 4.3) --------------------
    # Guarantee at least one NULL defect and at least one inconsistent defect.
    # The NULL defect goes to customers.city (a table with a generous cap of 3
    # for the standard 30-row dataset); the inconsistent defect also targets a
    # string column so it loads cleanly.
    _try_place("customers", "city", "null")
    _try_place("orders", "status", "inconsistent")

    # Fallbacks: if a preferred table had no capacity (e.g. an atypically small
    # dataset), place the mandatory defect types in any table with capacity so
    # the "at least one of each type" and "at least one overall" guarantees
    # hold whenever any capacity exists at all.
    if not any(r.defect_type == "null" for r in summary.records):
        for table, column in DEFECT_TARGETS:
            if _try_place(table, column, "null"):
                break
    if not any(r.defect_type == "inconsistent" for r in summary.records):
        # Inconsistent values only make sense on string columns; skip stock.
        for table, column in DEFECT_TARGETS:
            if column == "stock":
                continue
            if _try_place(table, column, "inconsistent"):
                break

    # --- Additional defects up to each table's cap ------------------------
    # Fill remaining capacity deterministically, cycling through the eligible
    # targets. products.stock only ever takes "null" defects (INT + CHECK);
    # string columns alternate defect types by an rng draw for variety.
    for table, column in DEFECT_TARGETS:
        while defects_per_table[table] < per_table_cap.get(table, 0):
            if column == "stock":
                defect_type = "null"
            else:
                defect_type = rng.choice(["null", "inconsistent"])
            if not _try_place(table, column, defect_type):
                break

    return summary


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def _format_cell(value: Any) -> str:
    """Render a single cell value for CSV output.

    A ``None`` value (a NULL in a nullable column) becomes an empty cell so the
    loader can map empty back to SQL NULL rather than the string ``"None"``
    (Requirement 9.3). ``date`` values are emitted in ISO 8601 (``YYYY-MM-DD``)
    format so they round-trip cleanly. Every other value is rendered with
    ``str`` and quoted as needed by the CSV writer.
    """
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def write_csvs(
    tables: Dict[str, List[Dict[str, Any]]], output_dir: str = "data"
) -> List[str]:
    """Write the five tables to CSV files under ``output_dir``.

    Writes exactly five files named for the five tables — ``categories.csv``,
    ``products.csv``, ``customers.csv``, ``orders.csv``, and
    ``order_details.csv`` — into ``output_dir`` (Requirements 6.1, 6.2). Files
    are written in the foreign-key-safe order of :data:`TABLE_NAMES`.

    Each file begins with a header row of the table's column names taken from
    :data:`TABLE_COLUMNS` (Requirement 6.3), followed by one row per record in
    the same column order. A ``None`` value is written as an empty cell so a
    nullable column round-trips to SQL NULL on load (Requirement 9.3); ``date``
    values are written in ISO format.

    The ``output_dir`` is created if it does not already exist (Requirement
    6.4). Files from a previous run are overwritten with the current output
    because each file is opened in write ("w") mode (Requirement 6.5).

    Args:
        tables: Mapping of table name to its rows (list of column-keyed dicts).
            Must contain every name in :data:`TABLE_NAMES`.
        output_dir: Directory to write the CSV files into. Defaults to
            ``"data"``.

    Returns:
        The list of file paths written, in :data:`TABLE_NAMES` order.

    Raises:
        GenerationError: If ``tables`` is missing one of the five tables, or if
            writing any CSV file fails. The error message identifies the
            specific file that could not be written (Requirement 6.6).
    """
    # Ensure the output directory exists before writing (Requirement 6.4).
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as exc:
        raise GenerationError(
            f"Failed to create output directory {output_dir!r}: {exc}"
        ) from exc

    written: List[str] = []
    for table_name in TABLE_NAMES:
        if table_name not in tables:
            raise GenerationError(
                f"Cannot write CSVs: missing table {table_name!r} in the "
                "generated dataset."
            )

        columns = TABLE_COLUMNS[table_name]
        rows = tables[table_name]
        file_path = os.path.join(output_dir, f"{table_name}.csv")

        try:
            # "w" truncates an existing file, overwriting stale output on a
            # re-run (Requirement 6.5). newline="" is required for the csv
            # module to control line terminators correctly across platforms.
            with open(file_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(columns)  # header row (Requirement 6.3)
                for row in rows:
                    writer.writerow(
                        [_format_cell(row.get(column)) for column in columns]
                    )
        except OSError as exc:
            # Identify the specific file that could not be written (Req 6.6).
            raise GenerationError(
                f"Failed to write CSV file {file_path!r}: {exc}"
            ) from exc

        written.append(file_path)

    return written


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def generate(
    seed: int = DEFAULT_SEED,
    output_dir: str = "data",
    generation_date: Optional[date] = None,
) -> GenerationResult:
    """Generate the full e-commerce dataset and export it as CSV files.

    The pipeline builds valid parent-then-child records, snapshots
    ``order_details.unit_price`` from each product's ``price``, validates
    referential integrity in memory, injects bounded data-quality defects into
    nullable non-key columns, writes the five CSVs to ``output_dir``, and
    returns a :class:`GenerationResult` carrying the defect summary.

    Args:
        seed: Random seed. A fixed seed yields byte-identical output across
            runs (Requirement 2.7). All randomness derives from the single
            ``random.Random`` instance created here.
        output_dir: Directory to write the five CSV files into; created if it
            does not exist.
        generation_date: The reference "now" for date windows. Defaults to
            :meth:`date.today` when ``None``. All registration and order dates
            fall within the 365 days preceding this date, inclusive.

    Returns:
        A :class:`GenerationResult` with the generated tables and defect summary.

    Raises:
        GenerationError: On referential-integrity or price-resolution failure,
            or if a CSV file cannot be written. On failure no partial output
            is produced.
    """
    # Single seeded RNG so every downstream draw is stable and ordered.
    rng = random.Random(seed)

    if generation_date is None:
        generation_date = date.today()

    # Build valid parent-then-child records in FK-safe order, threading the
    # single seeded RNG through every builder so the whole run is deterministic
    # for a fixed seed (Requirement 2.7).
    categories = build_categories(rng)
    customers = build_customers(rng, generation_date)
    products = build_products(rng, categories)
    orders = build_orders(rng, customers, generation_date)
    order_details = build_order_details(rng, orders, products)

    # Assemble the tables mapping keyed by the canonical, FK-safe table names.
    tables: Dict[str, List[Dict[str, Any]]] = {
        "categories": categories,
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_details": order_details,
    }

    # Validate referential integrity in memory BEFORE any file is written, so a
    # failure aborts the run with zero output (Requirement 2.8). Validation
    # runs on clean keys, before defects are injected.
    validate_referential_integrity(tables)

    # Inject bounded data-quality defects into nullable non-key columns. This
    # happens after validation because defects never touch keys, so referential
    # integrity is preserved (Requirement 4.x). The returned summary describes
    # exactly the cells that were altered (Requirement 4.6).
    summary = inject_defects(rng, tables)

    # Write the five CSVs to output_dir (Requirement 6.1). Any write failure
    # raises GenerationError from within write_csvs.
    write_csvs(tables, output_dir)

    return GenerationResult(tables=tables, defect_summary=summary)


if __name__ == "__main__":
    result = generate()
    print(f"Generated {len(result.defect_summary.records)} data-quality defects.")
