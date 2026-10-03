-- PUB-04 migration 0004 (UP): server-side auth sessions + OAuth flow states.
-- SQLite-compatible DDL (Postgres strategy: TEXT->TEXT, INTEGER->BIGINT —
-- see docs/deployment/database.md; PUB-05 finalizes the Neon migration set).

-- Server-side session store (PUB-04). Opaque bearer tokens: the cookie holds
-- the raw token, the row holds only its sha256 hash. Logout revokes the row
-- (server-side invalidation — SECURITY threat notes). The csrf_token backs
-- the double-submit CSRF check (S6) for real (non-stub) sessions.
CREATE TABLE auth_sessions (
    id          TEXT PRIMARY KEY,
    token_hash  TEXT NOT NULL UNIQUE,
    user_id     TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider    TEXT NOT NULL CHECK (provider IN ('github', 'fake-github', 'local-stub')),
    csrf_token  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions (user_id);

-- OAuth authorization-flow states (PUB-04): the CSRF `state` parameter and
-- the PKCE code_verifier are server-held; a state row is single-use
-- (consumed_at) and expires after 10 minutes.
CREATE TABLE oauth_states (
    state         TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    consumed_at   TEXT,
    next_path     TEXT
);
