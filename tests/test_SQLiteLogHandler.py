import unittest
import logging
import sqlite3
import os
import json
import time
import threading
import tempfile
import shutil
from typing import List, Dict, Any
from random import randint

# Import the SQLiteLogHandler class - assuming it's in a module called sqlite_log_handler
# If your module name is different, adjust this import
from python_sqlite_log_handler import SQLiteLogHandler


class test_SQLiteLogHandler(unittest.TestCase):
    """Test cases for the SQLiteLogHandler class using file-based SQLite databases."""

    def setUp(self):
        """Set up test fixtures before each test."""
        # Create temporary directory for test databases
        self.test_dir = tempfile.mkdtemp(prefix=f'sqlite_log_test_{randint(1000, 9999)}')

        # Create a file-based database for testing
        self.db_path = os.path.join(
            self.test_dir, f'test_logs_{randint(1000, 9999)}.db')

        self.table_name = "test_logs"
        self.handler = SQLiteLogHandler(
            db_path=self.db_path,
            table_name=self.table_name,
            capacity=100,
            flush_interval=0.5,  # Short interval for testing
            additional_fields=[
                ("test_field", "TEXT"),
                ("request_id", "TEXT")
            ]
        )

        # Create a logger
        self.logger = logging.getLogger("test_logger")
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)

        # Clear any existing handlers to avoid interference
        for handler in self.logger.handlers[:]:
            if handler != self.handler:
                self.logger.removeHandler(handler)

    def tearDown(self):
        """Clean up after each test."""
        self.handler.close()

        # Remove the test directory and all database files
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _get_all_logs(self, table_name=None) -> List[Dict[str, Any]]:
        """Helper method to retrieve all logs from the database."""
        if table_name is None:
            table_name = self.table_name

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cursor.fetchone():
            conn.close()
            return []

        cursor.execute(f"SELECT * FROM {table_name}")

        columns = [col[0] for col in cursor.description]
        results = []

        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('extra'):
                try:
                    result['extra'] = json.loads(result['extra'])
                except:
                    pass
            results.append(result)

        conn.close()
        return results

    def test_basic_logging(self):
        """Test that basic log messages are stored correctly."""
        test_message = "This is a test log message"
        self.logger.info(test_message)

        # Force flush to ensure logs are written
        self.handler.flush()

        logs = self._get_all_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['level_name'], 'INFO')
        self.assertIn(test_message, logs[0]['message'])
        self.assertEqual(logs[0]['logger_name'], 'test_logger')

        # Verify the file actually exists on disk
        self.assertTrue(os.path.exists(self.db_path))

        # Check file size is non-zero
        self.assertGreater(os.path.getsize(self.db_path), 0)

    def test_log_levels(self):
        """Test that different log levels are stored correctly."""
        self.logger.debug("Debug message")
        self.logger.info("Info message")
        self.logger.warning("Warning message")
        self.logger.error("Error message")
        self.logger.critical("Critical message")

        self.handler.flush()

        logs = self._get_all_logs()
        self.assertEqual(len(logs), 5)

        # Sort logs by level
        logs.sort(key=lambda x: x['level'])

        self.assertEqual(logs[0]['level_name'], 'DEBUG')
        self.assertEqual(logs[1]['level_name'], 'INFO')
        self.assertEqual(logs[2]['level_name'], 'WARNING')
        self.assertEqual(logs[3]['level_name'], 'ERROR')
        self.assertEqual(logs[4]['level_name'], 'CRITICAL')

    def test_exception_logging(self):
        """Test that exceptions are properly captured."""
        try:
            1 / 0
        except ZeroDivisionError:
            self.logger.exception("Caught an exception", exc_info=True)

        self.handler.flush()

        logs = self._get_all_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['level_name'], 'ERROR')
        self.assertIn("division by zero", logs[0]['exception'])

    def test_extra_fields(self):
        """Test that extra fields are stored correctly."""
        extra = {
            'test_field': 'test_value',
            'request_id': '12345',
            'custom_data': {'key': 'value'}
        }

        self.logger.info("Message with extra fields", extra=extra)
        self.handler.flush()

        logs = self._get_all_logs()
        self.assertEqual(len(logs), 1)

        # Check the remaining extra data was saved as JSON
        self.assertIn('custom_data', logs[0]['extra'])
        self.assertEqual(logs[0]['extra']['custom_data']['key'], 'value')

    def test_buffer_capacity(self):
        """Test that logs are flushed when buffer capacity is reached."""
        # Create a file for this specific test
        capacity_db_path = os.path.join(
            self.test_dir, f"capacity_test_{randint(1000, 9999)}.db")

        # Create a handler with small capacity
        small_capacity = 5
        handler = SQLiteLogHandler(
            db_path=capacity_db_path,
            table_name="capacity_test",
            capacity=small_capacity,
            flush_interval=60  # Long interval to ensure capacity triggers flush
        )

        logger = logging.getLogger("capacity_test")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        # Log slightly fewer messages than capacity
        for i in range(small_capacity - 1):
            logger.info(f"Message {i}")  # pylint: disable=W1203

        # Verify no logs yet (buffer not full)
        conn = sqlite3.connect(capacity_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM capacity_test")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

        # Log one more message to trigger flush
        logger.info("Final message")

        # Check all messages were flushed
        conn = sqlite3.connect(capacity_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM capacity_test")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, small_capacity)

        # Clean up
        handler.close()

        # Verify the database file exists and has content
        self.assertTrue(os.path.exists(capacity_db_path))
        self.assertGreater(os.path.getsize(capacity_db_path), 0)

    def test_periodic_flush(self):
        """Test that logs are flushed periodically."""
        # Create a file for this specific test
        interval_db_path = os.path.join(
            self.test_dir, f"interval_test_{randint(1000, 9999)}.db")

        # Create a handler with short flush interval
        handler = SQLiteLogHandler(
            db_path=interval_db_path,
            table_name="interval_test",
            capacity=1000,  # Large capacity to ensure timer triggers flush
            flush_interval=0.5  # Short interval for testing
        )

        logger = logging.getLogger("interval_test")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        # Log a message
        logger.info("Interval test message")

        # Wait for flush interval
        time.sleep(1.0)  # Slightly longer than flush_interval

        # Check message was flushed
        conn = sqlite3.connect(interval_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM interval_test")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

        # Clean up
        handler.close()

        # Verify the database file exists and has content
        self.assertTrue(os.path.exists(interval_db_path))
        self.assertGreater(os.path.getsize(interval_db_path), 0)

    def test_thread_safety(self):
        """Test that the handler is thread-safe."""
        # Create a file for this specific test
        thread_db_path = os.path.join(
            self.test_dir, f"thread_test_{randint(1000, 9999)}.db")

        # Create a handler specifically for thread testing
        thread_handler = SQLiteLogHandler(
            db_path=thread_db_path,
            table_name="thread_logs",
            capacity=200,
            flush_interval=1.0
        )

        num_threads = 10
        logs_per_thread = 50

        def log_from_thread(thread_id):
            thread_logger = logging.getLogger(f"thread_{thread_id}")
            thread_logger.setLevel(logging.DEBUG)
            thread_logger.addHandler(thread_handler)

            for i in range(logs_per_thread):
                thread_logger.info(f"Thread {thread_id} - Log {i}", extra={'thread_data': thread_id})  # pylint: disable=W1203

        # Create and start threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=log_from_thread, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Ensure flush
        thread_handler.flush()

        # Check database file exists and has content
        self.assertTrue(os.path.exists(thread_db_path))
        self.assertGreater(os.path.getsize(thread_db_path), 0)

        # Connect to check contents
        conn = sqlite3.connect(thread_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM thread_logs")
        count = cursor.fetchone()[0]
        conn.close()

        # Check all logs were stored
        self.assertEqual(count, num_threads * logs_per_thread)

        # Clean up
        thread_handler.close()

    def test_close_handler(self):
        """Test that close flushes records and releases resources."""
        # Create a file for this specific test
        close_db_path = os.path.join(
            self.test_dir, f"close_test_{randint(1000, 9999)}.db")

        # Create a handler
        handler = SQLiteLogHandler(
            db_path=close_db_path,
            table_name="close_test",
            capacity=100,
            flush_interval=10.0  # Long enough that we won't get an automatic flush
        )

        logger = logging.getLogger("close_test")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        # Log a message
        logger.info("Message before close")

        # Close the handler
        handler.close()

        # Check the message was flushed
        conn = sqlite3.connect(close_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM close_test")
        count = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(count, 1)

        # Verify thread was stopped
        self.assertTrue(handler.flush_thread_stop.is_set())
        self.assertFalse(handler.flush_thread.is_alive())

    def test_multiple_databases(self):
        """Test that multiple database files can be used simultaneously."""
        # Create two different database files
        db_path1 = os.path.join(self.test_dir, f"multi_test1_{randint(1000, 9999)}.db")
        db_path2 = os.path.join(self.test_dir, f"multi_test2_{randint(1000, 9999)}.db")

        # Create handlers for each database
        handler1 = SQLiteLogHandler(
            db_path=db_path1,
            table_name="logs1",
            capacity=10
        )

        handler2 = SQLiteLogHandler(
            db_path=db_path2,
            table_name="logs2",
            capacity=10
        )

        # Create loggers
        logger1 = logging.getLogger("multi_logger1")
        logger1.setLevel(logging.DEBUG)
        logger1.addHandler(handler1)

        logger2 = logging.getLogger("multi_logger2")
        logger2.setLevel(logging.DEBUG)
        logger2.addHandler(handler2)

        # Log to both
        logger1.info("Message to database 1")
        logger2.info("Message to database 2")

        # Flush both handlers
        handler1.flush()
        handler2.flush()

        # Verify each database has the correct logs
        conn1 = sqlite3.connect(db_path1)
        cursor1 = conn1.cursor()
        cursor1.execute("SELECT message FROM logs1")
        messages1 = cursor1.fetchall()
        conn1.close()

        conn2 = sqlite3.connect(db_path2)
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT message FROM logs2")
        messages2 = cursor2.fetchall()
        conn2.close()

        self.assertEqual(len(messages1), 1)
        self.assertEqual(len(messages2), 1)
        self.assertIn("Message to database 1", messages1[0][0])
        self.assertIn("Message to database 2", messages2[0][0])

        # Clean up
        handler1.close()
        handler2.close()

    def test_database_persistence(self):
        """Test that logs persist between handler instances."""
        persistence_db_path = os.path.join(
            self.test_dir, f"persistence_test_{randint(1000, 9999)}.db")
        table_name = "persistence_logs"

        # Create first handler and log a message
        handler1 = SQLiteLogHandler(
            db_path=persistence_db_path,
            table_name=table_name,
            capacity=10
        )

        logger = logging.getLogger("persistence_test")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler1)

        logger.info("Message from first handler")
        handler1.flush()
        handler1.close()

        # Create second handler and check if message exists
        handler2 = SQLiteLogHandler(
            db_path=persistence_db_path,
            table_name=table_name,
            capacity=10
        )

        # Log another message with second handler
        logger.handlers = [handler2]
        logger.info("Message from second handler")
        handler2.flush()

        # Check both messages exist
        conn = sqlite3.connect(persistence_db_path)
        cursor = conn.cursor()
        cursor.execute(f"SELECT message FROM {table_name}")
        messages = cursor.fetchall()
        conn.close()

        self.assertEqual(len(messages), 2)
        self.assertTrue(any("first handler" in msg[0] for msg in messages))
        self.assertTrue(any("second handler" in msg[0] for msg in messages))

        # Clean up
        handler2.close()


if __name__ == "__main__":
    unittest.main()
