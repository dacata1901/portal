"""Consistent backup and atomic restore helpers for SQLite and PostgreSQL."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_TABLES = ("users", "events", "registrations", "idempotency_records")


def _is_postgres(db_target):
    return isinstance(db_target, str) and db_target.startswith(("postgresql://", "postgres://"))


def _canonical_sha256(tables):
    payload = json.dumps(tables, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _credential_snapshot(conn, is_pg):
    if is_pg:
        exists = conn.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name='account_credentials'").fetchone()
    else:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_credentials'").fetchone()
    return [] if not exists else [dict(r) for r in conn.execute(
        'SELECT user_id,email_key,student_key,password_hash,created_at FROM account_credentials ORDER BY user_id').fetchall()]


def _clear_account_state(conn):
    # Sessions are deliberately revoked on restore, never copied into backups.
    for table in ('account_sessions', 'account_credentials', 'account_rate_limits'):
        conn.execute(f'DELETE FROM {table}')


def _restore_account_credentials(conn, tables, p):
    for row in tables.get('account_credentials', []):
        conn.execute(f'INSERT INTO account_credentials VALUES({p},{p},{p},{p},{p})',
                     (row['user_id'], row['email_key'], row['student_key'], row['password_hash'], row['created_at']))


def _sqlite_audit_on_conn(conn):
    rows = conn.execute(
        "SELECT e.id,e.capacity,COUNT(r.id) active,e.capacity-COUNT(r.id) remaining "
        "FROM events e LEFT JOIN registrations r ON r.event_id=e.id AND r.status='active' GROUP BY e.id"
    ).fetchall()
    duplicates = conn.execute(
        "SELECT user_id,event_id,COUNT(*) n FROM registrations "
        "WHERE status='active' GROUP BY user_id,event_id HAVING COUNT(*)>1"
    ).fetchall()
    foreign_keys = [tuple(r) for r in conn.execute("PRAGMA foreign_key_check")]
    return {
        "ok": not duplicates and all(0 <= r["remaining"] <= r["capacity"] for r in rows),
        "events": [dict(r) for r in rows],
        "duplicates": [dict(r) for r in duplicates],
        "foreignKeys": foreign_keys,
    }


def _postgres_audit_on_conn(conn):
    rows = conn.execute(
        """SELECT e.id,e.capacity,COUNT(r.id) FILTER (WHERE r.status='active') AS active,
           e.capacity-COUNT(r.id) FILTER (WHERE r.status='active') AS remaining
           FROM events e LEFT JOIN registrations r ON r.event_id=e.id
           GROUP BY e.id"""
    ).fetchall()
    duplicates = conn.execute(
        """SELECT user_id,event_id,COUNT(*) AS n FROM registrations
           WHERE status='active' GROUP BY user_id,event_id HAVING COUNT(*)>1"""
    ).fetchall()
    return {
        "ok": not duplicates and all(0 <= row["remaining"] <= row["capacity"] for row in rows),
        "events": rows,
        "duplicates": duplicates,
        "foreignKeys": [],
    }


def create_backup(db_target, output_path):
    """Create a checksummed point-in-time JSON backup of the portal database."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    is_pg = _is_postgres(db_target)

    if is_pg:
        from backend import postgres as pg

        with pg.connect(db_target) as conn:
            conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                tables = {
                    "users": conn.execute("SELECT id,student_id,name,email,role FROM users ORDER BY id").fetchall(),
                    "events": conn.execute("SELECT id,name,starts_at,capacity,metadata FROM events ORDER BY id").fetchall(),
                    "registrations": conn.execute(
                        "SELECT id,user_id,event_id,status,created_at,cancelled_at FROM registrations ORDER BY id"
                    ).fetchall(),
                    "idempotency_records": conn.execute(
                        "SELECT user_id,operation,request_id,fingerprint,http_status,response "
                        "FROM idempotency_records ORDER BY user_id,operation,request_id"
                    ).fetchall(),
                }
                tables['account_credentials'] = _credential_snapshot(conn, True)
                audit_snapshot = _postgres_audit_on_conn(conn)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    else:
        db_path = Path(db_target)
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        src = sqlite3.connect(str(db_path), timeout=15)
        mem = sqlite3.connect(":memory:")
        try:
            src.backup(mem)
            mem.row_factory = sqlite3.Row
            mem.execute("PRAGMA foreign_keys=ON")
            tables = {
                "users": [dict(r) for r in mem.execute("SELECT id,student_id,name,email,role FROM users ORDER BY id")],
                "events": [dict(r) for r in mem.execute("SELECT id,name,starts_at,capacity,metadata FROM events ORDER BY id")],
                "registrations": [
                    dict(r)
                    for r in mem.execute(
                        "SELECT id,user_id,event_id,status,created_at,cancelled_at FROM registrations ORDER BY id"
                    )
                ],
                "idempotency_records": [
                    dict(r)
                    for r in mem.execute(
                        "SELECT user_id,operation,request_id,fingerprint,http_status,response "
                        "FROM idempotency_records ORDER BY user_id,operation,request_id"
                    )
                ],
            }
            tables['account_credentials'] = _credential_snapshot(mem, False)
            audit_snapshot = _sqlite_audit_on_conn(mem)
        finally:
            mem.close()
            src.close()

    checksum = _canonical_sha256(tables)
    bundle = {
        "format": "campus-portal-backup-v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "engine": "postgres" if is_pg else "sqlite",
        "sha256": checksum,
        "audit": audit_snapshot,
        "tables": tables,
    }
    out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "outputPath": str(out),
        "engine": bundle["engine"],
        "createdAt": bundle["createdAt"],
        "sha256": checksum,
        "counts": {name: len(rows) for name, rows in tables.items()},
        "audit": audit_snapshot,
    }


def restore_backup(db_target, input_path):
    """Verify backup integrity and atomically restore all portal tables, then audit."""
    src_file = Path(input_path)
    bundle = json.loads(src_file.read_text(encoding="utf-8"))
    tables = bundle.get("tables")
    expected_sha = bundle.get("sha256")
    if not isinstance(tables, dict) or not all(isinstance(tables.get(t), list) for t in _TABLES):
        raise ValueError("Invalid backup structure")
    if _canonical_sha256(tables) != expected_sha:
        raise ValueError("Backup checksum mismatch")
    if 'account_credentials' in tables and not isinstance(tables['account_credentials'], list):
        raise ValueError('Invalid account credentials backup')

    if _is_postgres(db_target):
        from backend import postgres as database

        database.migrate(db_target)
        from backend.accounts import AccountStore
        AccountStore(database, db_target, '%s').migrate()
        with database.connect(db_target) as conn:
            conn.execute("BEGIN")
            try:
                _clear_account_state(conn)
                for table in ("idempotency_records", "registrations", "events", "users"):
                    conn.execute(f"DELETE FROM {table}")
                for u in tables["users"]:
                    conn.execute(
                        "INSERT INTO users(id,student_id,name,email,role) VALUES (%s,%s,%s,%s,%s)",
                        (u["id"], u.get("student_id"), u["name"], u["email"], u["role"]),
                    )
                for e in tables["events"]:
                    conn.execute(
                        "INSERT INTO events(id,name,starts_at,capacity,metadata) VALUES (%s,%s,%s,%s,%s)",
                        (e["id"], e["name"], e["starts_at"], e["capacity"], e["metadata"]),
                    )
                for r in tables["registrations"]:
                    conn.execute(
                        "INSERT INTO registrations(id,user_id,event_id,status,created_at,cancelled_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (r["id"], r["user_id"], r["event_id"], r["status"], r["created_at"], r.get("cancelled_at")),
                    )
                for rec in tables["idempotency_records"]:
                    conn.execute(
                        "INSERT INTO idempotency_records(user_id,operation,request_id,fingerprint,http_status,response) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        (
                            rec["user_id"],
                            rec["operation"],
                            rec["request_id"],
                            rec["fingerprint"],
                            rec["http_status"],
                            rec["response"],
                        ),
                    )
                _restore_account_credentials(conn, tables, '%s')
                conn.execute("COMMIT")
            except Exception:
                if not conn.closed:
                    conn.execute("ROLLBACK")
                raise
    else:
        from backend import db as database

        database.migrate(db_target)
        from backend.accounts import AccountStore
        AccountStore(database, db_target).migrate()
        conn = database.connect(db_target)
        try:
            conn.execute("BEGIN IMMEDIATE")
            _clear_account_state(conn)
            for table in ("idempotency_records", "registrations", "events", "users"):
                conn.execute(f"DELETE FROM {table}")
            for u in tables["users"]:
                conn.execute(
                    "INSERT INTO users(id,student_id,name,email,role) VALUES (?,?,?,?,?)",
                    (u["id"], u.get("student_id"), u["name"], u["email"], u["role"]),
                )
            for e in tables["events"]:
                conn.execute(
                    "INSERT INTO events(id,name,starts_at,capacity,metadata) VALUES (?,?,?,?,?)",
                    (e["id"], e["name"], e["starts_at"], e["capacity"], e["metadata"]),
                )
            for r in tables["registrations"]:
                conn.execute(
                    "INSERT INTO registrations(id,user_id,event_id,status,created_at,cancelled_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (r["id"], r["user_id"], r["event_id"], r["status"], r["created_at"], r.get("cancelled_at")),
                )
            for rec in tables["idempotency_records"]:
                conn.execute(
                    "INSERT INTO idempotency_records(user_id,operation,request_id,fingerprint,http_status,response) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        rec["user_id"],
                        rec["operation"],
                        rec["request_id"],
                        rec["fingerprint"],
                        rec["http_status"],
                        rec["response"],
                    ),
                )
            _restore_account_credentials(conn, tables, '?')
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    audit_result = database.audit(db_target)
    if not audit_result["ok"] or audit_result["foreignKeys"]:
        raise RuntimeError("Restored database failed audit checks")
    return audit_result
