import sqlite3
from pathlib import Path


# ============================================================
# KUNAL QUANT
# DATABASE SCHEMA
# ============================================================

SCHEMA_VERSION = 1


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;


-- ==========================================================
-- SCHEMA METADATA
-- ==========================================================

CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);


-- ==========================================================
-- INSTRUMENT MASTER
-- ==========================================================

CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    broker TEXT NOT NULL,
    exchange TEXT NOT NULL,
    segment TEXT NOT NULL,

    symbol TEXT NOT NULL,

    broker_token TEXT,
    security_id TEXT,

    underlying TEXT,

    instrument_type TEXT NOT NULL,

    expiry_date TEXT,
    strike REAL,
    option_type TEXT,

    lot_size INTEGER,
    tick_size REAL,

    currency TEXT DEFAULT 'INR',

    is_active INTEGER DEFAULT 1,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (broker, symbol)
);


CREATE INDEX IF NOT EXISTS idx_instruments_symbol
ON instruments(symbol);


CREATE INDEX IF NOT EXISTS idx_instruments_underlying
ON instruments(underlying);


CREATE INDEX IF NOT EXISTS idx_instruments_expiry
ON instruments(expiry_date);


CREATE INDEX IF NOT EXISTS idx_instruments_option_type
ON instruments(option_type);


-- ==========================================================
-- HISTORICAL CANDLES
-- ==========================================================

CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    instrument_id INTEGER NOT NULL,

    timestamp INTEGER NOT NULL,

    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,

    volume INTEGER,
    open_interest INTEGER,

    resolution TEXT NOT NULL,
    source TEXT NOT NULL,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (instrument_id)
        REFERENCES instruments(id)
        ON DELETE CASCADE,

    UNIQUE (
        instrument_id,
        timestamp,
        resolution,
        source
    )
);


CREATE INDEX IF NOT EXISTS idx_candles_instrument_timestamp
ON candles(instrument_id, timestamp);


CREATE INDEX IF NOT EXISTS idx_candles_timestamp
ON candles(timestamp);


-- ==========================================================
-- DOWNLOAD JOBS
-- ==========================================================

CREATE TABLE IF NOT EXISTS download_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    broker TEXT NOT NULL,
    symbol TEXT NOT NULL,

    resolution TEXT NOT NULL,

    range_from TEXT NOT NULL,
    range_to TEXT NOT NULL,

    status TEXT NOT NULL,

    requested_candles INTEGER DEFAULT 0,
    received_candles INTEGER DEFAULT 0,
    inserted_candles INTEGER DEFAULT 0,
    duplicate_candles INTEGER DEFAULT 0,
    missing_candles INTEGER DEFAULT 0,

    retry_count INTEGER DEFAULT 0,

    error_message TEXT,

    started_at TEXT,
    completed_at TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX IF NOT EXISTS idx_download_jobs_symbol
ON download_jobs(symbol);


CREATE INDEX IF NOT EXISTS idx_download_jobs_status
ON download_jobs(status);


-- ==========================================================
-- DATA QUALITY EVENTS
-- ==========================================================

CREATE TABLE IF NOT EXISTS data_quality_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    instrument_id INTEGER,
    timestamp INTEGER,

    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,

    description TEXT,

    detected_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (instrument_id)
        REFERENCES instruments(id)
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_quality_instrument
ON data_quality_events(instrument_id);


CREATE INDEX IF NOT EXISTS idx_quality_type
ON data_quality_events(event_type);


-- ==========================================================
-- TRADING SESSIONS
-- ==========================================================

CREATE TABLE IF NOT EXISTS trading_sessions (
    trade_date TEXT PRIMARY KEY,

    exchange TEXT NOT NULL,

    market_open TEXT NOT NULL,
    market_close TEXT NOT NULL,

    expected_minutes INTEGER NOT NULL,
    actual_minutes INTEGER DEFAULT 0,

    status TEXT DEFAULT 'unknown',

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);


-- ==========================================================
-- DATASETS
-- ==========================================================

CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    dataset_name TEXT UNIQUE NOT NULL,

    description TEXT,

    broker TEXT,
    asset_class TEXT,
    timeframe TEXT,

    date_from TEXT,
    date_to TEXT,

    instrument_count INTEGER DEFAULT 0,
    candle_count INTEGER DEFAULT 0,

    status TEXT DEFAULT 'created',

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);


-- ==========================================================
-- BACKTEST RUNS
-- ==========================================================

CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    strategy_name TEXT NOT NULL,
    strategy_version TEXT,

    instrument TEXT,

    date_from TEXT,
    date_to TEXT,

    timeframe TEXT,

    initial_capital REAL,
    final_capital REAL,

    pnl REAL,

    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,

    max_drawdown REAL,
    profit_factor REAL,

    status TEXT DEFAULT 'created',

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);


-- ==========================================================
-- BACKTEST TRADES
-- ==========================================================

CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    backtest_run_id INTEGER NOT NULL,

    trade_number INTEGER,

    trade_date TEXT,

    symbol TEXT,

    option_type TEXT,
    strike REAL,
    expiry_date TEXT,

    entry_time INTEGER,
    entry_price REAL,

    exit_time INTEGER,
    exit_price REAL,

    quantity INTEGER,

    gross_pnl REAL,
    charges REAL,
    net_pnl REAL,

    stop_loss REAL,
    target REAL,
    rr REAL,

    exit_reason TEXT,

    FOREIGN KEY (backtest_run_id)
        REFERENCES backtest_runs(id)
        ON DELETE CASCADE
);


CREATE INDEX IF NOT EXISTS idx_backtest_trades_run
ON backtest_trades(backtest_run_id);


-- ==========================================================
-- STRATEGY EXPERIMENTS
-- Future ML/self-learning system
-- ==========================================================

CREATE TABLE IF NOT EXISTS strategy_experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    strategy_name TEXT NOT NULL,

    base_version TEXT,
    proposed_version TEXT,

    change_summary TEXT,

    evidence TEXT,

    approval_status TEXT DEFAULT 'pending',

    approved_by TEXT,
    approved_at TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);


-- ==========================================================
-- TRADE LEARNING / REVIEW
-- Future self-learning system
-- ==========================================================

CREATE TABLE IF NOT EXISTS trade_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    backtest_trade_id INTEGER,

    review_type TEXT,

    finding TEXT,

    severity TEXT,

    proposed_change TEXT,

    status TEXT DEFAULT 'pending',

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (backtest_trade_id)
        REFERENCES backtest_trades(id)
        ON DELETE CASCADE
);


-- ==========================================================
-- INITIAL SCHEMA VERSION
-- ==========================================================

"""


# ------------------------------------------------------------
# DATABASE INITIALIZATION
# ------------------------------------------------------------

def initialize_database(
    database_path: Path | str
) -> None:

    database_path = Path(database_path)

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        database_path
    )

    try:

        connection.executescript(
            SCHEMA_SQL
        )

        connection.execute(
            """
            INSERT INTO schema_metadata (key, value)
            VALUES (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (
                "schema_version",
                str(SCHEMA_VERSION)
            )
        )

        connection.commit()

    finally:

        connection.close()


# ------------------------------------------------------------
# CONNECTION
# ------------------------------------------------------------

def get_connection(
    database_path: Path | str
) -> sqlite3.Connection:

    database_path = Path(database_path)

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        database_path
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# ------------------------------------------------------------
# LIST TABLES
# ------------------------------------------------------------

def get_table_names(
    database_path: Path | str
) -> list[str]:

    connection = get_connection(
        database_path
    )

    try:

        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()

        return [
            row[0]
            for row in rows
        ]

    finally:

        connection.close()


# ------------------------------------------------------------
# TEST
# ------------------------------------------------------------

if __name__ == "__main__":

    from config.settings import DATABASE_PATH

    print("=" * 70)
    print("KUNAL QUANT - DATABASE INITIALIZATION")
    print("=" * 70)

    print("\nDatabase:")
    print(DATABASE_PATH)

    print("\nInitializing database...")

    initialize_database(
        DATABASE_PATH
    )

    tables = get_table_names(
        DATABASE_PATH
    )

    print("\nTables created:")

    for table in tables:
        print(f"  [OK] {table}")

    print("\nDatabase ready.")

    print("=" * 70)