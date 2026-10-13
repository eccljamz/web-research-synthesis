"""Persistent SQLite Caching Engine for Document Retrieval.

Pure Python Standard Library (3.10+) - Zero External Dependencies.
Provides durable disk-backed caching for raw web documents and search query results
using SQLite3 with TTL eviction, connection management, and atomic transactions.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from research_synthesis.models import RawWebDocument
except ImportError:
    from src.research_synthesis.models import RawWebDocument

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "research_synthesis"
DEFAULT_CACHE_PATH = DEFAULT_CACHE_DIR / "http_cache.db"


class SQLiteDocumentCache:
    """Thread-safe, persistent SQLite cache for RawWebDocument instances and search queries."""

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        default_ttl: int = 86400,  # 24 hours
    ):
        """Initialize SQLite cache with path and default TTL.

        Args:
            db_path: Path to SQLite database file. Defaults to ~/.cache/research_synthesis/http_cache.db.
            default_ttl: Default retention period in seconds (default: 86400s / 24 hours).
        """
        if db_path is None:
            db_path = DEFAULT_CACHE_PATH
        self.db_path = Path(db_path)
        self.default_ttl = default_ttl
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Create and yield an SQLite connection, ensuring it is cleanly closed upon exit."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Ensure parent directories and database tables exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_cache (
                    url TEXT PRIMARY KEY,
                    status_code INTEGER,
                    headers_json TEXT,
                    raw_html TEXT,
                    error TEXT,
                    fetched_at REAL,
                    expires_at REAL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS search_cache (
                    query TEXT PRIMARY KEY,
                    urls_json TEXT,
                    fetched_at REAL,
                    expires_at REAL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_doc_expires ON document_cache(expires_at);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_search_expires ON search_cache(expires_at);
                """
            )

    def get_document(self, url: str) -> Optional[RawWebDocument]:
        """Retrieve a cached RawWebDocument if present and not expired."""
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT status_code, headers_json, raw_html, error, expires_at FROM document_cache WHERE url = ?",
                (url,),
            )
            row = cur.fetchone()
            if not row:
                return None

            if row["expires_at"] and row["expires_at"] < now:
                # Expired
                cur.execute("DELETE FROM document_cache WHERE url = ?", (url,))
                return None

            headers = json.loads(row["headers_json"]) if row["headers_json"] else {}
            return RawWebDocument(
                url=url,
                status_code=row["status_code"],
                headers=headers,
                raw_html=row["raw_html"] or "",
                error=row["error"],
            )

    def put_document(
        self,
        doc: RawWebDocument,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Store or update a RawWebDocument in the cache."""
        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expires_at = now + ttl if ttl > 0 else 0.0

        headers_json = json.dumps(doc.headers) if doc.headers else "{}"
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO document_cache (url, status_code, headers_json, raw_html, error, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    status_code = excluded.status_code,
                    headers_json = excluded.headers_json,
                    raw_html = excluded.raw_html,
                    error = excluded.error,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at;
                """,
                (doc.url, doc.status_code, headers_json, doc.raw_html, doc.error, now, expires_at),
            )

    def get_search(self, query: str) -> Optional[List[str]]:
        """Retrieve cached search query URLs if present and not expired."""
        now = time.time()
        norm_q = query.strip().lower()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT urls_json, expires_at FROM search_cache WHERE query = ?",
                (norm_q,),
            )
            row = cur.fetchone()
            if not row:
                return None

            if row["expires_at"] and row["expires_at"] < now:
                cur.execute("DELETE FROM search_cache WHERE query = ?", (norm_q,))
                return None

            try:
                return json.loads(row["urls_json"])
            except Exception:
                return None

    def put_search(
        self,
        query: str,
        urls: List[str],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache search result URLs for a query."""
        now = time.time()
        norm_q = query.strip().lower()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expires_at = now + ttl if ttl > 0 else 0.0
        urls_json = json.dumps(urls)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO search_cache (query, urls_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(query) DO UPDATE SET
                    urls_json = excluded.urls_json,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at;
                """,
                (norm_q, urls_json, now, expires_at),
            )

    def clear(self) -> None:
        """Purge all entries from the cache."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM document_cache;")
            conn.execute("DELETE FROM search_cache;")

    def count(self) -> Tuple[int, int]:
        """Return (document_count, search_query_count)."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM document_cache;")
            doc_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM search_cache;")
            search_count = cur.fetchone()[0]
            return doc_count, search_count

    def prune_expired(self) -> int:
        """Remove all expired records from cache. Returns number of purged records."""
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM document_cache WHERE expires_at > 0 AND expires_at < ?", (now,))
            docs_pruned = cur.rowcount
            cur.execute("DELETE FROM search_cache WHERE expires_at > 0 AND expires_at < ?", (now,))
            search_pruned = cur.rowcount
            return docs_pruned + search_pruned
