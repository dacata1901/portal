BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, student_id TEXT UNIQUE, name TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('student','organizer','administrator')));
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, name TEXT NOT NULL, starts_at TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity>=0), metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS registrations(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), event_id TEXT NOT NULL REFERENCES events(id), status TEXT NOT NULL CHECK(status IN ('active','cancelled')), created_at TEXT NOT NULL, cancelled_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_active ON registrations(user_id,event_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS idempotency_records(user_id TEXT NOT NULL REFERENCES users(id), operation TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, http_status INTEGER NOT NULL, response TEXT NOT NULL, PRIMARY KEY(user_id,operation,request_id));
CREATE TRIGGER IF NOT EXISTS capacity_insert BEFORE INSERT ON registrations WHEN NEW.status='active' BEGIN
 SELECT CASE WHEN (SELECT COUNT(*) FROM registrations WHERE event_id=NEW.event_id AND status='active') >= (SELECT capacity FROM events WHERE id=NEW.event_id) THEN RAISE(ABORT,'capacity exceeded') END;
END;
CREATE TRIGGER IF NOT EXISTS capacity_update BEFORE UPDATE OF status,event_id ON registrations WHEN NEW.status='active' BEGIN
 SELECT CASE WHEN (SELECT COUNT(*) FROM registrations WHERE event_id=NEW.event_id AND status='active' AND id<>OLD.id) >= (SELECT capacity FROM events WHERE id=NEW.event_id) THEN RAISE(ABORT,'capacity exceeded') END;
END;
CREATE TRIGGER IF NOT EXISTS capacity_reduce BEFORE UPDATE OF capacity ON events BEGIN
 SELECT CASE WHEN NEW.capacity < (SELECT COUNT(*) FROM registrations WHERE event_id=OLD.id AND status='active') THEN RAISE(ABORT,'capacity below registrations') END;
END;
PRAGMA user_version=1;
COMMIT;
