"""Repository_Connection: read/validate connection parameters and open a
connection to the AWS_Database (Amazon RDS for PostgreSQL).

Design reference: design.md "3. Repository_Connection (`db/connection.py`)".

Behavioral contract (Requirement 8):
- Parameters (`host`, `port`, `dbname`, `user`, `password`) come only from the
  gitignored `.env` file / environment (AC 8.1).
- ``load_config`` validates all five parameters and raises ``ConfigError``
  listing *every* missing or invalid parameter by name, so a single failed
  call surfaces all problems at once (AC 8.3).
- ``connect`` opens a psycopg2 connection with a 10-second timeout and, on an
  unreachable host or rejected authentication, raises ``ConnectionFailure``
  chained to the underlying cause (AC 8.4). A returned connection has had its
  ability to run queries confirmed (AC 8.2).

Credentials are referenced by *name* only. Secret values (notably the
password) are never included in exception messages or logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Required parameters
# ---------------------------------------------------------------------------

# The five connection parameters, in a stable order. Names are used verbatim
# both as `.env` keys and as psycopg2 connect() keyword arguments.
REQUIRED_PARAMS: List[str] = ["host", "port", "dbname", "user", "password"]

# Parameters whose values are secret and must never be echoed in errors/logs.
_SECRET_PARAMS = frozenset({"password"})


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when connection parameters are missing or invalid.

    The message names every offending parameter (Requirement 8.3) so the caller
    can fix all of them at once. Secret values are never included -- only the
    parameter *name* and a non-sensitive reason are reported.
    """

    def __init__(self, problems: Dict[str, str]):
        # ``problems`` maps a parameter name to a short, non-sensitive reason.
        self.problems = dict(problems)
        detail = "; ".join(
            f"{name}: {reason}" for name, reason in self.problems.items()
        )
        super().__init__(
            "Invalid connection configuration for parameter(s): " + detail
        )


class ConnectionFailure(Exception):
    """Raised when a connection cannot be established (Requirement 8.4).

    Covers an unreachable host or rejected authentication. The originating
    exception is attached as the cause (via ``raise ... from``) so the reason is
    inspectable without leaking the password value.
    """


# ---------------------------------------------------------------------------
# Connection configuration model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectionConfig:
    """Validated set of AWS_Database connection parameters.

    ``port`` is stored as an ``int``. The password is held here so it can be
    passed to psycopg2, but it is deliberately excluded from ``__repr__`` /
    logging output below so it never leaks into diagnostics.
    """

    host: str
    port: int
    dbname: str
    user: str
    password: str

    def __repr__(self) -> str:  # pragma: no cover - trivial formatting
        # Never expose the password; reference it by name only.
        return (
            "ConnectionConfig("
            f"host={self.host!r}, port={self.port!r}, "
            f"dbname={self.dbname!r}, user={self.user!r}, "
            "password=***)"
        )

    __str__ = __repr__


# ---------------------------------------------------------------------------
# Loading & validation
# ---------------------------------------------------------------------------


def load_config(env_path: str = ".env") -> ConnectionConfig:
    """Read and validate the five connection parameters.

    Values are sourced only from ``env_path`` (a ``.env`` file) and the process
    environment (AC 8.1). ``python-dotenv`` is used to read the file without
    mutating the real process environment.

    Raises:
        ConfigError: If one or more parameters are missing or invalid. Every
            offending parameter is named in the error (AC 8.3). Secret values
            are never included.
    """
    from dotenv import dotenv_values
    import os

    # Start from the .env file (if present), then let real environment
    # variables override, so deployment-time env vars win over a checked-out
    # file. Missing files yield an empty mapping rather than an error.
    values: Dict[str, Optional[str]] = {}
    file_values = dotenv_values(env_path)
    for key in REQUIRED_PARAMS:
        if key in file_values and file_values[key] is not None:
            values[key] = file_values[key]
        elif key in os.environ:
            values[key] = os.environ[key]
        else:
            values[key] = None

    problems: Dict[str, str] = {}

    # Validate string parameters: present and non-empty (after stripping).
    for name in ("host", "dbname", "user", "password"):
        raw = values.get(name)
        if raw is None or str(raw).strip() == "":
            problems[name] = "missing or empty"

    # Validate port: present and a positive integer in the valid TCP range.
    raw_port = values.get("port")
    port_int: Optional[int] = None
    if raw_port is None or str(raw_port).strip() == "":
        problems["port"] = "missing or empty"
    else:
        try:
            port_int = int(str(raw_port).strip())
        except (TypeError, ValueError):
            # Do not echo the raw value -- it could be anything; name only.
            problems["port"] = "must be an integer"
        else:
            if not (1 <= port_int <= 65535):
                problems["port"] = "must be between 1 and 65535"

    if problems:
        raise ConfigError(problems)

    assert port_int is not None  # guaranteed when no problems recorded
    return ConnectionConfig(
        host=str(values["host"]).strip(),
        port=port_int,
        dbname=str(values["dbname"]).strip(),
        user=str(values["user"]).strip(),
        password=str(values["password"]),
    )


# ---------------------------------------------------------------------------
# Connecting
# ---------------------------------------------------------------------------


def connect(config: ConnectionConfig, timeout_seconds: int = 10):
    """Open a psycopg2 connection with a bounded timeout.

    Establishes a connection using ``connect_timeout`` so an unreachable host
    fails within ``timeout_seconds`` (default 10s, AC 8.4). Before returning,
    the connection state is confirmed by executing ``SELECT 1`` so the caller
    receives a connection on which queries are known to run (AC 8.2).

    Raises:
        ConnectionFailure: On an unreachable host or rejected authentication.
            The underlying psycopg2 error is chained as the cause; the password
            value is never included in the message.
    """
    import psycopg2

    try:
        conn = psycopg2.connect(
            host=config.host,
            port=config.port,
            dbname=config.dbname,
            user=config.user,
            password=config.password,
            connect_timeout=timeout_seconds,
            sslmode="require",
        )
    except Exception as exc:  # psycopg2.OperationalError and friends
        # Reference credentials by name only; do not echo the password value.
        raise ConnectionFailure(
            f"Could not connect to database '{config.dbname}' at "
            f"{config.host}:{config.port} as user '{config.user}' "
            f"within {timeout_seconds}s"
        ) from exc

    # Confirm the connection can actually run queries (AC 8.2).
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception as exc:
        try:
            conn.close()
        finally:
            raise ConnectionFailure(
                f"Connected to '{config.dbname}' at {config.host}:{config.port} "
                "but the connection could not execute a query"
            ) from exc

    return conn
