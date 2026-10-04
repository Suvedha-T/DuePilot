SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
    user_id TEXT PRIMARY KEY,
    preference TEXT DEFAULT 'Balanced',
    daily_available_hours REAL DEFAULT 5.0,
    buffer_percent REAL DEFAULT 0.20,
    focus_block_length_hours REAL DEFAULT 1.5,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    sender TEXT NOT NULL,
    subject TEXT,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS responsibilities (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT DEFAULT 'Academic',
    description TEXT,
    deadline TIMESTAMP,
    deadline_str TEXT,
    estimated_hours REAL DEFAULT 1.0,
    consequence_score REAL DEFAULT 50.0,
    importance_score REAL DEFAULT 50.0,
    difficulty_level INTEGER DEFAULT 3,
    status TEXT DEFAULT 'pending',
    source_id TEXT,
    is_blocked INTEGER DEFAULT 0,
    blocker_reason TEXT,
    priority_score REAL DEFAULT 0.0,
    priority_data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    responsibility_id TEXT NOT NULL,
    title TEXT NOT NULL,
    estimated_minutes INTEGER DEFAULT 30,
    status TEXT DEFAULT 'pending',
    order_idx INTEGER DEFAULT 0,
    is_blocked INTEGER DEFAULT 0,
    blocker_reason TEXT,
    FOREIGN KEY (responsibility_id) REFERENCES responsibilities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dependencies (
    id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    dependency_type TEXT DEFAULT 'depends_on',
    description TEXT
);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    preference_mode TEXT DEFAULT 'Balanced',
    total_workload_hours REAL DEFAULT 0.0,
    available_hours REAL DEFAULT 5.0,
    buffer_hours REAL DEFAULT 1.0,
    is_overloaded INTEGER DEFAULT 0,
    plan_data_json TEXT,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS schedule_blocks (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    title TEXT NOT NULL,
    responsibility_id TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_minutes INTEGER DEFAULT 90,
    block_type TEXT DEFAULT 'task',
    priority_score REAL DEFAULT 0.0,
    notes TEXT,
    FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plan_diffs (
    id TEXT PRIMARY KEY,
    previous_plan_id TEXT,
    new_plan_id TEXT NOT NULL,
    trigger_event TEXT NOT NULL,
    reason TEXT NOT NULL,
    diff_data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_events (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    agent_name TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT DEFAULT 'success',
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS communication_drafts (
    id TEXT PRIMARY KEY,
    recipient TEXT NOT NULL,
    channel TEXT DEFAULT 'WhatsApp',
    subject TEXT,
    body TEXT NOT NULL,
    status TEXT DEFAULT 'proposed',
    reason TEXT NOT NULL,
    related_responsibility_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
