-- Invite links for onboarding new editors.
--
-- An invite is single-use, bound to one email address, and expires. Only the
-- SHA-256 hash of the token is stored: the raw token exists solely in the link
-- the admin copies, so a database dump cannot be replayed into editor access.
CREATE TABLE IF NOT EXISTS user_invites (
    id SERIAL PRIMARY KEY,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'editor',
    created_by VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    redeemed_at TIMESTAMP WITH TIME ZONE,
    redeemed_by VARCHAR(255) REFERENCES users(id) ON DELETE SET NULL,
    revoked_at TIMESTAMP WITH TIME ZONE
);

-- Redemption looks an invite up by token hash on every attempt.
CREATE INDEX IF NOT EXISTS idx_user_invites_token_hash ON user_invites(token_hash);

-- The admin list is ordered newest-first.
CREATE INDEX IF NOT EXISTS idx_user_invites_created_at ON user_invites(created_at DESC);
