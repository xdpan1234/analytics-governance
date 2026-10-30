"""Connections inherit role-specific credentials from the process environment."""
import os
import psycopg
from psycopg.rows import dict_row

SCOPE = os.environ.get("ANALYTICS_SCOPE", "ai.looktech.glasses.memo/prod/us/release")


def connect(read_only=False):
    options = "-c statement_timeout=10000 -c timezone=UTC -c search_path=analytics,pg_catalog"
    if read_only:
        options += " -c default_transaction_read_only=on"
    return psycopg.connect(connect_timeout=5, options=options, row_factory=dict_row)
