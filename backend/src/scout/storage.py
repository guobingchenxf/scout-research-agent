"""SQLite persistence for documents, runs, events, evidence and the audit chain."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import (
    Approval,
    Chunk,
    Citation,
    Event,
    Evidence,
    Run,
    RunStatus,
    SourceDocument,
    utc_now,
)

GENESIS_HASH = "0" * 64


class StorageError(Exception):
    """Raised when persistence fails in a way the caller must handle."""


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class SQLiteStore:
    """A small, inspectable store.

    One connection guarded by a re-entrant lock. This is intentionally
    single-node: the benchmark and the agent run in one process, and SQLite is
    enough for a reproducible evaluation.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            source_type TEXT NOT NULL,
            trust TEXT NOT NULL,
            retrieval_method TEXT NOT NULL,
            license TEXT,
            published_at TEXT,
            fetched_at TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            text TEXT NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(doc_id, ordinal)
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            constraints_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ended_at TEXT,
            result_json TEXT,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            ts TEXT NOT NULL,
            UNIQUE(run_id, seq)
        );
        CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, seq);

        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            claim TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            span TEXT NOT NULL DEFAULT '',
            quote TEXT NOT NULL DEFAULT '',
            trust TEXT NOT NULL,
            support TEXT NOT NULL,
            retrieval_method TEXT NOT NULL,
            content_hash TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id);

        CREATE TABLE IF NOT EXISTS citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL DEFAULT '',
            doc_id TEXT NOT NULL,
            span TEXT NOT NULL DEFAULT '',
            quote TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_citations_run ON citations(run_id);

        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            question TEXT NOT NULL,
            risk TEXT NOT NULL,
            options_json TEXT NOT NULL DEFAULT '[]',
            decision TEXT,
            decided_by TEXT,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            decided_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_approvals_run ON approvals(run_id);

        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL DEFAULT '',
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            decision TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL,
            ts TEXT NOT NULL
        );
        """
        with self._lock, self._conn:
            self._conn.executescript(schema)

    # ------------------------------------------------------------------
    # Documents and chunks
    # ------------------------------------------------------------------
    def upsert_document(self, doc: SourceDocument) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO documents (
                    id, title, url, source_type, trust, retrieval_method,
                    license, published_at, fetched_at, content_hash, text, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    url=excluded.url,
                    source_type=excluded.source_type,
                    trust=excluded.trust,
                    retrieval_method=excluded.retrieval_method,
                    license=excluded.license,
                    published_at=excluded.published_at,
                    fetched_at=excluded.fetched_at,
                    content_hash=excluded.content_hash,
                    text=excluded.text,
                    metadata_json=excluded.metadata_json
                """,
                (
                    doc.id,
                    doc.title,
                    doc.url,
                    doc.source_type.value,
                    doc.trust.value,
                    doc.retrieval_method.value,
                    doc.license,
                    doc.published_at,
                    doc.fetched_at,
                    doc.content_hash,
                    doc.text,
                    json.dumps(doc.metadata, ensure_ascii=False),
                ),
            )

    def replace_chunks(self, doc_id: str, chunks: Iterable[Chunk]) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self._conn.executemany(
                "INSERT INTO chunks (id, doc_id, ordinal, text, token_count) VALUES (?, ?, ?, ?, ?)",
                [(c.id, c.doc_id, c.ordinal, c.text, c.token_count) for c in chunks],
            )

    def ingest_document(self, doc: SourceDocument, chunks: Iterable[Chunk]) -> None:
        chunk_list = list(chunks)
        with self._lock, self._conn:
            self.upsert_document(doc)
            self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc.id,))
            self._conn.executemany(
                "INSERT INTO chunks (id, doc_id, ordinal, text, token_count) VALUES (?, ?, ?, ?, ?)",
                [(c.id, c.doc_id, c.ordinal, c.text, c.token_count) for c in chunk_list],
            )

    def get_document(self, doc_id: str) -> SourceDocument | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return self._row_to_document(row) if row else None

    def list_documents(self) -> list[SourceDocument]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM documents ORDER BY id").fetchall()
        return [self._row_to_document(row) for row in rows]

    def list_chunks(self) -> list[Chunk]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, doc_id, ordinal, text, token_count FROM chunks ORDER BY doc_id, ordinal"
            ).fetchall()
        return [
            Chunk(
                id=row["id"],
                doc_id=row["doc_id"],
                ordinal=row["ordinal"],
                text=row["text"],
                token_count=row["token_count"],
            )
            for row in rows
        ]

    def count_documents(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()
        return int(row["n"])

    def count_chunks(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        return int(row["n"])

    def _row_to_document(self, row: sqlite3.Row) -> SourceDocument:
        return SourceDocument(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            source_type=row["source_type"],
            trust=row["trust"],
            retrieval_method=row["retrieval_method"],
            license=row["license"],
            published_at=row["published_at"],
            fetched_at=row["fetched_at"],
            content_hash=row["content_hash"],
            text=row["text"],
            metadata=_loads(row["metadata_json"], {}),
        )

    # ------------------------------------------------------------------
    # Runs and events
    # ------------------------------------------------------------------
    def create_run(self, run: Run) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO runs (id, question, constraints_json, status, created_at, ended_at, result_json, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.question,
                    json.dumps(run.constraints, ensure_ascii=False),
                    run.status.value,
                    run.created_at,
                    run.ended_at,
                    json.dumps(run.result, ensure_ascii=False) if run.result is not None else None,
                    run.error,
                ),
            )

    def update_run(
        self,
        run_id: str,
        *,
        status: RunStatus | None = None,
        ended_at: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status.value)
        if ended_at is not None:
            fields.append("ended_at = ?")
            values.append(ended_at)
        if result is not None:
            fields.append("result_json = ?")
            values.append(json.dumps(result, ensure_ascii=False))
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        if not fields:
            return
        values.append(run_id)
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", values)

    def get_run(self, run_id: str) -> Run | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return Run(
            id=row["id"],
            question=row["question"],
            constraints=_loads(row["constraints_json"], {}),
            status=row["status"],
            created_at=row["created_at"],
            ended_at=row["ended_at"],
            result=_loads(row["result_json"], None),
            error=row["error"],
        )

    def append_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> Event:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS seq FROM events WHERE run_id = ?", (run_id,)
            ).fetchone()
            seq = int(row["seq"]) + 1
            ts = utc_now()
            self._conn.execute(
                "INSERT INTO events (run_id, seq, type, payload_json, ts) VALUES (?, ?, ?, ?, ?)",
                (run_id, seq, event_type, json.dumps(payload, ensure_ascii=False), ts),
            )
        return Event(seq=seq, type=event_type, payload=payload, ts=ts)

    def list_events(self, run_id: str) -> list[Event]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, type, payload_json, ts FROM events WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
        return [
            Event(seq=row["seq"], type=row["type"], payload=_loads(row["payload_json"], {}), ts=row["ts"])
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Evidence, citations, approvals
    # ------------------------------------------------------------------
    def add_evidence(self, run_id: str, evidence: Evidence) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO evidence (
                    id, run_id, claim, doc_id, span, quote, trust, support,
                    retrieval_method, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id,
                    run_id,
                    evidence.claim,
                    evidence.doc_id,
                    evidence.span,
                    evidence.quote,
                    evidence.trust.value,
                    evidence.support.value,
                    evidence.retrieval_method.value,
                    evidence.content_hash,
                ),
            )

    def list_evidence(self, run_id: str) -> list[Evidence]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM evidence WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [
            Evidence(
                id=row["id"],
                claim=row["claim"],
                doc_id=row["doc_id"],
                span=row["span"],
                quote=row["quote"],
                trust=row["trust"],
                support=row["support"],
                retrieval_method=row["retrieval_method"],
                content_hash=row["content_hash"],
            )
            for row in rows
        ]

    def add_citation(self, run_id: str, citation: Citation) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO citations (run_id, evidence_id, doc_id, span, quote, url)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    citation.evidence_id,
                    citation.doc_id,
                    citation.span,
                    citation.quote,
                    citation.url,
                ),
            )

    def list_citations(self, run_id: str) -> list[Citation]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT evidence_id, doc_id, span, quote, url FROM citations WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [
            Citation(
                evidence_id=row["evidence_id"],
                doc_id=row["doc_id"],
                span=row["span"],
                quote=row["quote"],
                url=row["url"],
            )
            for row in rows
        ]

    def add_approval(self, approval: Approval) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO approvals (
                    id, run_id, question, risk, options_json, decision,
                    decided_by, note, created_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.id,
                    approval.run_id,
                    approval.question,
                    approval.risk,
                    json.dumps(approval.options, ensure_ascii=False),
                    approval.decision,
                    approval.decided_by,
                    approval.note,
                    approval.created_at,
                    approval.decided_at,
                ),
            )

    def decide_approval(self, approval_id: str, decision: str, decided_by: str, note: str = "") -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                UPDATE approvals
                SET decision = ?, decided_by = ?, note = ?, decided_at = ?
                WHERE id = ? AND decision IS NULL
                """,
                (decision, decided_by, note, utc_now(), approval_id),
            )
        return cursor.rowcount > 0

    def list_approvals(self, run_id: str) -> list[Approval]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM approvals WHERE run_id = ? ORDER BY created_at", (run_id,)
            ).fetchall()
        return [
            Approval(
                id=row["id"],
                run_id=row["run_id"],
                question=row["question"],
                risk=row["risk"],
                options=_loads(row["options_json"], []),
                decision=row["decision"],
                decided_by=row["decided_by"],
                note=row["note"],
                created_at=row["created_at"],
                decided_at=row["decided_at"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Audit hash chain
    # ------------------------------------------------------------------
    def append_audit(self, run_id: str, actor: str, action: str, decision: str) -> dict[str, Any]:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT entry_hash FROM audit ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = row["entry_hash"] if row else GENESIS_HASH
            record = {
                "run_id": run_id,
                "actor": actor,
                "action": action,
                "decision": decision,
                "prev_hash": prev_hash,
            }
            entry_hash = hashlib.sha256(
                (prev_hash + _canonical(record)).encode("utf-8")
            ).hexdigest()
            ts = utc_now()
            self._conn.execute(
                """
                INSERT INTO audit (run_id, actor, action, decision, prev_hash, entry_hash, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, actor, action, decision, prev_hash, entry_hash, ts),
            )
        return {"prev_hash": prev_hash, "entry_hash": entry_hash, "ts": ts}

    def verify_audit(self) -> tuple[bool, int | None]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, run_id, actor, action, decision, prev_hash, entry_hash FROM audit ORDER BY id"
            ).fetchall()
        expected_prev = GENESIS_HASH
        for row in rows:
            record = {
                "run_id": row["run_id"],
                "actor": row["actor"],
                "action": row["action"],
                "decision": row["decision"],
                "prev_hash": expected_prev,
            }
            expected_hash = hashlib.sha256(
                (expected_prev + _canonical(record)).encode("utf-8")
            ).hexdigest()
            if row["prev_hash"] != expected_prev or row["entry_hash"] != expected_hash:
                return False, int(row["id"])
            expected_prev = row["entry_hash"]
        return True, None

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def clear(self) -> None:
        with self._lock, self._conn:
            for table in (
                "citations",
                "evidence",
                "approvals",
                "events",
                "audit",
                "runs",
                "chunks",
                "documents",
            ):
                self._conn.execute(f"DELETE FROM {table}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()
