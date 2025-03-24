# Python SQLite Log Handler

[![build](https://github.com/rogervila/python_sqlite_log_handler/actions/workflows/build.yml/badge.svg)](https://github.com/rogervila/python_sqlite_log_handler/actions/workflows/build.yml)
[![CodeQL](https://github.com/rogervila/python_sqlite_log_handler/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/rogervila/python_sqlite_log_handler/actions/workflows/codeql-analysis.yml)
[![PyPI version](https://badge.fury.io/py/python-sqlite-log-handler.svg)](https://badge.fury.io/py/python-sqlite-log-handler)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A high-performance SQLite logging handler for Python that stores log messages in an SQLite database. Built on top of Python's `BufferingHandler`, it provides efficient logging with minimal I/O overhead.

## Features

- **High Performance**: Uses buffering to minimize disk I/O operations
- **Thread-Safe**: Designed to work in multi-threaded environments
- **Customizable Schema**: Add custom fields to log tables
- **Background Flushing**: Automatic periodic flushing of buffered logs
- **Optimized SQLite Settings**: Uses WAL mode, memory-mapped I/O, and increased cache size
- **Rich Log Data**: Captures comprehensive information for each log entry:
  - Basic log info (level, message, timestamp)
  - Source code context (filename, function, line number)
  - Thread and process information
  - Exception details with stack traces
  - Custom fields and extra data

## Installation

```bash
pip install python_sqlite_log_handler
```

## Basic Usage

```python
import logging
from python_sqlite_log_handler import SQLiteLogHandler

# Set up logging
logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)

# Create and add the handler to the logger
handler = SQLiteLogHandler(db_path="logs.db")
logger.addHandler(handler)

# Log some messages
logger.info("This is an info message")
logger.warning("This is a warning message")
logger.error("An error occurred", exc_info=True)

# Don't forget to close the handler when done
handler.close()
```

## Advanced Usage

### Custom Fields and Extra Data

You can define additional fields for your log entries and pass extra data when logging:

```python
from python_sqlite_log_handler import SQLiteLogHandler
import logging

# Create a handler with custom fields
custom_fields = [
    ("user_id", "TEXT"),
    ("request_id", "TEXT"),
    ("ip_address", "TEXT")
]

handler = SQLiteLogHandler(
    db_path="logs.db",
    table_name="application_logs",
    capacity=500,  # Flush every 500 logs
    flush_interval=10.0,  # Or every 10 seconds
    additional_fields=custom_fields
)

# Set up logger
logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

# Log with extra fields
extra = {
    "user_id": "user123",
    "request_id": "req-456-abc",
    "ip_address": "192.168.1.1",
    "custom_data": {"key": "value"}  # Will be stored in the extra JSON field
}

logger.info("User action performed", extra=extra)
```

### Working with Multiple Databases and Tables

You can create multiple handlers for different loggers or purposes:

```python
# Application logs
app_handler = SQLiteLogHandler(
    db_path="app_logs.db",
    table_name="app_events"
)

# Security logs in a separate database
security_handler = SQLiteLogHandler(
    db_path="security_logs.db",
    table_name="security_events",
    flush_interval=1.0  # Flush more frequently for security logs
)

# Set up loggers
app_logger = logging.getLogger("app")
app_logger.addHandler(app_handler)

security_logger = logging.getLogger("security")
security_logger.addHandler(security_handler)
```

### Querying Logs

Since logs are stored in SQLite, you can use SQL to query them:

```python
import sqlite3

# Connect to your log database
conn = sqlite3.connect("logs.db")
cursor = conn.cursor()

# Query logs by level and time
cursor.execute("""
    SELECT created_at, level_name, logger_name, message, extra
    FROM logs
    WHERE level >= ? AND created_at > ?
    ORDER BY created_at DESC
    LIMIT 100
""", (logging.WARNING, "2023-01-01T00:00:00"))

for row in cursor.fetchall():
    timestamp, level, logger, message, extra = row
    print(f"{timestamp} | {level:7s} | {logger:15s} | {message}")

conn.close()
```

## Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `db_path` | Path to the SQLite database file | (required) |
| `table_name` | Name of the table to store logs | `"logs"` |
| `capacity` | Number of records to buffer before writing | `1000` |
| `flush_interval` | Time in seconds between periodic flushes | `5.0` |
| `additional_fields` | List of (name, type) tuples for custom columns | `None` |

## SQLite Performance Optimizations

The handler automatically configures SQLite for optimal logging performance:

- **WAL Mode**: Enabled for better concurrency
- **Synchronous Mode**: Set to NORMAL for improved write performance
- **Cache Size**: Increased to 10MB
- **Memory-Mapped I/O**: Enabled with 256MB allocation
- **Indexes**: Created on commonly queried fields

## Thread Safety

The handler is designed to be thread-safe and can be used in multi-threaded applications. Each thread maintains its own database connection, and access to the buffer is protected by locks.

## License

This project is licensed under the MIT License - see the [LICENSE.txt](LICENSE.txt) file for details.
