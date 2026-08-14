-- CyberLab Agent v4.0
-- memory/schema.sql

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent TEXT NOT NULL,
    plan TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS mutations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    file_path TEXT,
    action TEXT,
    before_hash TEXT,
    after_hash TEXT,
    timestamp TEXT,
    rolled_back INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_pattern TEXT,
    solution TEXT,
    success_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS project_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE,
    file_hash TEXT,
    summary TEXT,
    last_scanned TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    ended_at TEXT,
    tasks_done INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    summary TEXT
);
