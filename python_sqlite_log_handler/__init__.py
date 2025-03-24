import logging
import sqlite3
import threading
import json
import traceback
from datetime import datetime
from logging.handlers import BufferingHandler
from typing import Any, Dict, List, Optional, Tuple, Union


class SQLiteLogHandler(BufferingHandler):
    """
    A logging handler that stores logs in an SQLite database.
    Uses buffering for improved performance and minimizes disk I/O.
    """

    def __init__(self,
                 db_path: str,
                 table_name: str = 'logs',
                 capacity: int = 1000,
                 flush_interval: float = 5.0,
                 additional_fields: Optional[List[Tuple[str, str]]] = None):
        """
        Initialize the handler with the path to the SQLite database.

        Args:
            db_path: Path to the SQLite database file
            table_name: Name of the table to store logs
            capacity: Number of records to buffer before writing to disk
            flush_interval: Time in seconds between periodic flushes
            additional_fields: List of (name, type) for additional columns to create
        """
        # Initialize with buffer capacity
        super().__init__(capacity)

        self.db_path = db_path
        self.table_name = table_name
        self.flush_interval = flush_interval
        self.additional_fields = additional_fields or []

        # Thread local storage for database connections
        self.local = threading.local()

        # Lock for thread safety
        self.lock = threading.RLock()

        # Initialize the database
        self._initialize_db()

        # Start background flush thread
        self._start_flush_thread()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self.local, 'conn'):
            self.local.conn = sqlite3.connect(self.db_path)
            # Enable WAL mode for better concurrency
            self.local.conn.execute('PRAGMA journal_mode=WAL')
            # Disable synchronous writes for better performance
            self.local.conn.execute('PRAGMA synchronous=NORMAL')
            # Increase cache size
            self.local.conn.execute('PRAGMA cache_size=-10000')  # ~10MB cache
            # Enable memory-mapped I/O
            self.local.conn.execute('PRAGMA mmap_size=268435456')  # 256MB
        return self.local.conn

    def _initialize_db(self) -> None:
        """Initialize the database table if it doesn't exist."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Build the basic schema
        schema = [
            "id INTEGER PRIMARY KEY AUTOINCREMENT",
            "created_at TIMESTAMP NOT NULL",
            "level INTEGER NOT NULL",
            "level_name TEXT NOT NULL",
            "logger_name TEXT NOT NULL",
            "message TEXT NOT NULL",
            "function_name TEXT",
            "module TEXT",
            "filename TEXT",
            "line_number INTEGER",
            "process_id INTEGER",
            "process_name TEXT",
            "thread_id INTEGER",
            "thread_name TEXT",
            "exception TEXT",
            "stack_trace TEXT",
            "extra JSON"
        ]

        # Add custom fields
        for field_name, field_type in self.additional_fields:
            schema.append(f"{field_name} {field_type}")

        # Create the table if it doesn't exist
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            {', '.join(schema)}
        )
        """
        cursor.execute(create_table_sql)

        # Create indexes for common query fields
        indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_created_at ON {self.table_name} (created_at)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_level ON {self.table_name} (level)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_logger_name ON {self.table_name} (logger_name)"
        ]

        for index_sql in indexes:
            cursor.execute(index_sql)

        conn.commit()

    def _start_flush_thread(self) -> None:
        """Start a background thread to periodically flush the buffer."""
        if self.flush_interval <= 0:
            return

        self.flush_thread = threading.Thread(
            target=self._flush_thread_run,
            daemon=True,
            name="SQLiteLogHandler-Flush"
        )
        self.flush_thread_stop = threading.Event()
        self.flush_thread.start()

    def _flush_thread_run(self) -> None:
        """Background thread that periodically flushes the buffer."""
        while not self.flush_thread_stop.wait(self.flush_interval):
            self.flush()

    def emit(self, record: logging.LogRecord) -> None:
        """Add the record to the buffer."""
        with self.lock:
            self.buffer.append(record)
            if len(self.buffer) >= self.capacity:
                self.flush()

    def _extract_record_data(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Extract all useful data from the log record."""
        # Basic record info
        data = {
            "created_at": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelno,
            "level_name": record.levelname,
            "logger_name": record.name,
            "message": self.format(record),
            "function_name": record.funcName,
            "module": record.module,
            "filename": record.pathname,
            "line_number": record.lineno,
            "process_id": record.process,
            "process_name": record.processName,
            "thread_id": record.thread,
            "thread_name": record.threadName,
            "exception": None,
            "stack_trace": None,
            "extra": None
        }

        # Handle exception info if present
        if record.exc_info:
            data["exception"] = str(record.exc_info[1])
            data["stack_trace"] = ''.join(
                traceback.format_exception(*record.exc_info))

        # Store extra attributes as JSON
        extra_attrs = {}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and key not in data:
                try:
                    # Try to make the value JSON serializable
                    json.dumps({key: value})
                    extra_attrs[key] = value
                except (TypeError, OverflowError):
                    # Skip non-serializable values
                    extra_attrs[key] = str(value)

        if extra_attrs:
            data["extra"] = json.dumps(extra_attrs)

        return data

    def flush(self) -> None:
        """Write all buffered records to the database."""
        if not self.buffer:
            return

        with self.lock:
            records = self.buffer
            self.buffer = []

        if not records:
            return

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # Prepare the SQL for batch insert
            record_data = self._extract_record_data(records[0])
            columns = list(record_data.keys())
            placeholders = ', '.join(['?'] * len(columns))

            insert_sql = f"""
            INSERT INTO {self.table_name} ({', '.join(columns)})
            VALUES ({placeholders})
            """

            # Extract data from all records
            values = []
            for record in records:
                record_data = self._extract_record_data(record)
                values.append(tuple(record_data[col] for col in columns))

            # Execute batch insert
            cursor.executemany(insert_sql, values)
            conn.commit()

        except Exception as e:
            # Don't let exceptions from the database affect the application
            print(f"Error in SQLiteLogHandler.flush: {e}")

    def close(self) -> None:
        """Close the handler and release resources."""
        # Stop background thread if running
        if hasattr(self, 'flush_thread') and self.flush_thread.is_alive():
            self.flush_thread_stop.set()
            self.flush_thread.join(timeout=1.0)

        # Final flush
        self.flush()

        # Close all thread-local connections
        if hasattr(self.local, 'conn'):
            try:
                self.local.conn.close()
            except:
                pass

        super().close()
