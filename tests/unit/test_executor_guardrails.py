import pytest

from agent.executor import UnsafeSQLError, execute_safe_query, validate_sql


def test_validate_sql_rejects_multiple_statements():
    with pytest.raises(UnsafeSQLError, match="Multiple SQL statements"):
        validate_sql("SELECT 1; SELECT 2;")


def test_validate_sql_rejects_non_select_statement():
    with pytest.raises(UnsafeSQLError, match="Only SELECT/CTE queries are allowed"):
        validate_sql("DELETE FROM fact_sales")


def test_validate_sql_rejects_multiple_statements_before_keyword_checks():
    with pytest.raises(UnsafeSQLError, match="Multiple SQL statements are not allowed"):
        validate_sql("WITH x AS (SELECT 1) SELECT * FROM x; DROP TABLE fact_sales;")


def test_execute_safe_query_rejects_invalid_limits():
    with pytest.raises(ValueError, match="row_limit must be positive"):
        execute_safe_query("SELECT 1", row_limit=0, timeout_ms=1000)

    with pytest.raises(ValueError, match="timeout_ms must be positive"):
        execute_safe_query("SELECT 1", row_limit=1, timeout_ms=0)


def test_execute_safe_query_sets_statement_timeout(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.executed = []
            self.description = [("value",)]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            self.executed.append((sql, params))

        def fetchall(self):
            return [(123,)]

    class FakeConn:
        def __init__(self):
            self.cursor_obj = FakeCursor()

        def cursor(self):
            return self.cursor_obj

        def close(self):
            return None

    class FakeSession:
        def __init__(self):
            self.conn = FakeConn()

        def __enter__(self):
            return self.conn, "psycopg"

        def __exit__(self, exc_type, exc, tb):
            self.conn.close()
            return False

    fake_session = FakeSession()
    monkeypatch.setenv("DB_ENGINE", "postgres")
    monkeypatch.setattr("agent.executor.db_session", lambda: fake_session)

    rows = execute_safe_query("SELECT 1 AS value", row_limit=5, timeout_ms=3210)
    assert rows == [{"value": 123}]
    assert fake_session.conn.cursor_obj.executed[0] == ("SET statement_timeout = '3210ms'", None)
    assert "LIMIT %s" in fake_session.conn.cursor_obj.executed[1][0]
    assert fake_session.conn.cursor_obj.executed[1][1] == (5,)
