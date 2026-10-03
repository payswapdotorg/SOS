-- PUB-04 migration 0004 (DOWN): revert auth sessions + OAuth flow states.

DROP TABLE oauth_states;
DROP TABLE auth_sessions;
