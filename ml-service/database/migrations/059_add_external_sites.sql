-- External sites (added 2026-11-19 at the owner's request: "a new admin screen: External Sites. I should be able to
-- provide a link to the site", first for the Kindle web reader). A shared list of sites the administrators open from
-- the Drupal "External sites" page (external_sites.py): a name, an http(s) address and notes. The site opens in its own
-- browser window beside the admin page, not in a frame: Amazon refuses to show its sign-in page inside another site,
-- and browsers keep a framed site's cookies apart, so a framed reader would stay signed out.
--
-- sign_in_address (optional, '' for none): the site's sign-in page, for a Sign in button beside Open (the owner asked
-- for "a link or button visible" for when one is not signed in: our page cannot see another site's sign-in).
--
-- Not in schema.sql; make-public-data.sh leaves its rows out. Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/059_add_external_sites.sql

CREATE TABLE IF NOT EXISTS admin_external_sites (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  address TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  sign_in_address TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE admin_external_sites ADD COLUMN IF NOT EXISTS sign_in_address TEXT NOT NULL DEFAULT '';
