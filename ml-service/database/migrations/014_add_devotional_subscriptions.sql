-- Visitors who get a devotional by email each day. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/014_add_devotional_subscriptions.sql
-- (locally: docker exec -i bible-and-beyond-database psql -U bibleandbeyond -v ON_ERROR_STOP=1 < database/migrations/014_add_devotional_subscriptions.sql)

CREATE TABLE IF NOT EXISTS devotional_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    -- A user has many subscriptions (one for each devotional); deleting the user deletes them.
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    -- The devotional by id. Not a foreign key: reloading a devotional must never take its subscribers away.
    devotional_id TEXT NOT NULL,
    -- When to send, as a clock time in the visitor's own time zone (an IANA name such as America/Chicago).
    send_time TIME NOT NULL,
    timezone TEXT NOT NULL,
    -- A devotional with chapters sends one a day, in order: the next one to send. NULL for a daily devotional,
    -- which sends the reading for the visitor's date.
    next_section INTEGER,
    next_unit INTEGER,
    -- The visitor's local date of the last email sent (or of today, while it is being sent).
    last_sent_on DATE,
    -- Failed tries on attempts_on, so a broken mail server is tried a few times a day and no more.
    attempts_on DATE,
    attempts INTEGER NOT NULL DEFAULT 0,
    -- In every email's unsubscribe link, so stopping needs no login. It can do nothing but stop this one.
    unsubscribe_token TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, devotional_id)
);
