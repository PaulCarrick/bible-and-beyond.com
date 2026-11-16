-- Prayer Wall requests emailed to a group or its leader (added 2026-11-16 at the owner's request: the Prayer Wall's
-- checkboxes became one "Who sees this request" list, with "Email <group>" and "Email the leader of <group>" for
-- a member of a group; either sends at once and makes the post private).
--
-- conversation_posts.share_group_id: the group (member_groups) it was emailed to; NULL if the group is deleted.
-- conversation_posts.share_with: 'group' (every member of it) or 'leader' (its leader only); NULL when not shared.
-- conversation_posts.shared_at: when the email went (NULL while it is still to go, or after the choice changed).
-- A shared request is private, and is left out of the administrators' prayer list email (listed_at NULL): it was
-- meant for the group or the leader.
--
-- Like the rest of conversation_posts it is not in schema.sql. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/046_add_prayer_group_sharing.sql

ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS share_group_id INTEGER REFERENCES member_groups (id) ON DELETE SET NULL;
ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS share_with TEXT;
ALTER TABLE conversation_posts ADD COLUMN IF NOT EXISTS shared_at TIMESTAMPTZ;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'conversation_posts_share_check') THEN
    ALTER TABLE conversation_posts ADD CONSTRAINT conversation_posts_share_check CHECK (
      share_with IS NULL OR (share_with IN ('group', 'leader') AND board = 'prayer' AND is_private)
    );
  END IF;
END
$$;
