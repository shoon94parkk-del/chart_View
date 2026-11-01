"""Durable learning accounts. PostgreSQL in production; explicit local SQLite only.

No connection or schema work occurs at import/startup. Each write holds an account
row lock and commits its document and idempotency receipt in one transaction.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg


class StoreError(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(detail)


def utcnow():
    return datetime.now(timezone.utc)


def digest(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class LearningStore:
    SESSION_DAYS = 30
    MAX_DOCUMENT_BYTES = 128 * 1024 * 1024

    def __init__(self, database_url=None, sqlite_path=None):
        self.database_url = database_url if database_url is not None else (
            os.environ.get("LEARNING_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
        self.sqlite_path = sqlite_path if sqlite_path is not None else os.environ.get("LEARNING_SQLITE_PATH", "").strip()
        self._schema_lock = threading.Lock()
        self._ready = False

    @property
    def storage(self):
        if self.database_url:
            return "postgres"
        if self.sqlite_path and not any(os.environ.get(key) for key in (
                "RENDER", "RENDER_SERVICE_ID", "RENDER_EXTERNAL_URL", "RENDER_INSTANCE_ID")):
            return "sqlite"
        return None

    @contextmanager
    def _connection(self, write=False):
        backend = self.storage
        if backend is None:
            raise StoreError(503, "기업 공부의 영구 저장소가 연결되지 않았습니다. PostgreSQL 설정을 확인해 주세요.")
        conn = None
        try:
            if backend == "postgres":
                conn = psycopg.connect(self.database_url, connect_timeout=5)
            else:
                if self.sqlite_path == ":memory:" or self.sqlite_path.startswith("file:"):
                    raise StoreError(503, "로컬 검증에는 명시적인 SQLite 파일 경로가 필요합니다.")
                conn = sqlite3.connect(self.sqlite_path, timeout=15)
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA busy_timeout = 15000")
            self._ensure_schema(conn)
            if backend == "sqlite":
                conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except (psycopg.Error, sqlite3.Error, OSError) as exc:
            if conn:
                conn.rollback()
            raise StoreError(503, "기업 공부 영구 저장소에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.") from exc
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    def _sql(self, conn, sql, params=()):
        return conn.execute(sql if self.storage == "postgres" else sql.replace("%s", "?"), params)

    def _ensure_schema(self, conn):
        if self._ready:
            return
        with self._schema_lock:
            if self._ready:
                return
            if self.storage == "postgres":
                conn.execute("SELECT pg_advisory_xact_lock(772024031)")
            conn.execute("""CREATE TABLE IF NOT EXISTS learning_accounts (
                id TEXT PRIMARY KEY, recovery_hash TEXT NOT NULL UNIQUE,
                document TEXT NOT NULL, created_at TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS learning_sessions (
                token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES learning_accounts(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL, created_at TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS learning_requests (
                account_id TEXT NOT NULL REFERENCES learning_accounts(id) ON DELETE CASCADE,
                request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL,
                created_at TEXT NOT NULL, PRIMARY KEY (account_id, request_id))""")
            conn.execute("CREATE INDEX IF NOT EXISTS learning_session_account ON learning_sessions(account_id)")
            conn.commit()
            self._ready = True

    def status(self):
        if not self.storage:
            return {"configured": False, "storage": None}
        try:
            with self._connection() as conn:
                conn.execute("SELECT 1")
        except StoreError:
            return {"configured": False, "storage": self.storage}
        return {"configured": True, "storage": self.storage}

    def _new_session(self, conn, account_id):
        token = secrets.token_urlsafe(32)
        now = utcnow()
        expires = now + timedelta(days=self.SESSION_DAYS)
        self._sql(conn, "INSERT INTO learning_sessions (token_hash, account_id, expires_at, created_at) VALUES (%s,%s,%s,%s)",
                  (digest(token), account_id, expires.isoformat(), now.isoformat()))
        self._sql(conn, "DELETE FROM learning_sessions WHERE account_id=%s AND expires_at<=%s", (account_id, now.isoformat()))
        return {"accountId": account_id, "token": token, "expiresAt": expires.isoformat()}

    def create_account(self, document):
        account_id, recovery = str(uuid4()), secrets.token_urlsafe(32)
        with self._connection(write=True) as conn:
            self._sql(conn, "INSERT INTO learning_accounts (id,recovery_hash,document,created_at) VALUES (%s,%s,%s,%s)",
                      (account_id, digest(recovery), json.dumps(document, ensure_ascii=False), utcnow().isoformat()))
            result = self._new_session(conn, account_id)
        return {**result, "recoveryKey": recovery}

    def recover(self, recovery):
        with self._connection(write=True) as conn:
            row = self._sql(conn, "SELECT id FROM learning_accounts WHERE recovery_hash=%s", (digest(recovery),)).fetchone()
            if not row:
                raise StoreError(401, "복구 키를 확인해 주세요.")
            return self._new_session(conn, row[0])

    def authenticate(self, token):
        with self._connection() as conn:
            row = self._sql(conn, "SELECT account_id FROM learning_sessions WHERE token_hash=%s AND expires_at>%s",
                            (digest(token), utcnow().isoformat())).fetchone()
            if not row:
                raise StoreError(401, "인증 세션이 없거나 만료되었습니다. 복구 키로 다시 연결해 주세요.")
            return row[0]

    def revoke(self, token):
        with self._connection(write=True) as conn:
            self._sql(conn, "DELETE FROM learning_sessions WHERE token_hash=%s", (digest(token),))

    def delete_account(self, account_id):
        with self._connection(write=True) as conn:
            self._sql(conn, "DELETE FROM learning_accounts WHERE id=%s", (account_id,))

    def read(self, account_id):
        with self._connection() as conn:
            row = self._sql(conn, "SELECT document FROM learning_accounts WHERE id=%s", (account_id,)).fetchone()
            if not row:
                raise StoreError(401, "계정이 삭제되었거나 인증이 만료되었습니다.")
            return json.loads(row[0])

    def transact(self, account_id, request_id, expected_version, fingerprint, mutation):
        with self._connection(write=True) as conn:
            suffix = " FOR UPDATE" if self.storage == "postgres" else ""
            row = self._sql(conn, "SELECT document FROM learning_accounts WHERE id=%s" + suffix, (account_id,)).fetchone()
            if not row:
                raise StoreError(401, "계정이 삭제되었거나 인증이 만료되었습니다.")
            receipt = self._sql(conn, "SELECT fingerprint,result FROM learning_requests WHERE account_id=%s AND request_id=%s",
                                (account_id, request_id)).fetchone()
            if receipt:
                if receipt[0] != fingerprint:
                    raise StoreError(409, "같은 요청 ID가 다른 내용에 사용되었습니다.")
                persisted = json.loads(receipt[1])
                current = json.loads(row[0])
                return {"workspace": {k: v for k, v in current.items() if not k.startswith("_")}, **persisted}
            document = json.loads(row[0])
            if document["version"] != expected_version:
                raise StoreError(409, "다른 기기에서 기록이 변경되었습니다. 작성 내용을 유지한 채 최신 기록을 불러와 주세요.")
            extra = mutation(document) or {}
            document["version"] += 1
            receipt_result = {"requestVersion": document["version"], **extra}
            result = {"workspace": {k: v for k, v in document.items() if not k.startswith("_")}, **receipt_result}
            encoded = json.dumps(document, ensure_ascii=False, allow_nan=False)
            if len(encoded.encode("utf-8")) > self.MAX_DOCUMENT_BYTES:
                raise StoreError(422, "계정 기록의 최대 저장 크기를 초과했습니다. 기존 기록은 유지됩니다. 백업을 보관하고 저장 용량 지원을 요청해 주세요.")
            self._sql(conn, "UPDATE learning_accounts SET document=%s WHERE id=%s", (encoded, account_id))
            self._sql(conn, "INSERT INTO learning_requests (account_id,request_id,fingerprint,result,created_at) VALUES (%s,%s,%s,%s,%s)",
                      (account_id, request_id, fingerprint, json.dumps(receipt_result, ensure_ascii=False, allow_nan=False), utcnow().isoformat()))
            return result
