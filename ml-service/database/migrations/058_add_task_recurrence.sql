-- A general "how often" for tasks (added 2026-11-19 at the owner's request: "the first .. of the .... For example
-- communion is on the first sunday of the month", then "It's not just the month", choosing every few months, once a
-- year, several weekdays and week-based). admin_tasks.repeat becomes one of:
--
--   weekly           every interval_count weeks (1 to 8) on the weekdays (0 Monday to 6 Sunday)
--   monthly_day      every interval_count months (1 to 12; 12 is once a year) on day_of_month (1 to 31; 29 to 31 the
--                    last day in shorter months)
--   monthly_weekday  every interval_count months on the weeks_of_month (1 to 4 the first to the fourth, 5 the last)
--                    of the weekdays: "the first Sunday", "the first and third Sunday", "the last Thursday"
--
-- first_date is the start: nothing comes before it, and every few weeks or months counts from its week or month (its
-- month is the month of a once-a-year task). Earlier tasks are converted: weekly keeps its weekday; every two weeks
-- (biweekly) becomes weekly every 2 weeks from its first date; monthly becomes monthly_day; tasks without a start
-- start on the day they were made. weekday stays, for older code, as the first of the weekdays.
--
-- Safe to run more than once.
--
-- Apply with:
--   psql -d bibleandbeyond -v ON_ERROR_STOP=1 -f database/migrations/058_add_task_recurrence.sql

ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS interval_count SMALLINT NOT NULL DEFAULT 1;
ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS weekdays SMALLINT[];
ALTER TABLE admin_tasks ADD COLUMN IF NOT EXISTS weeks_of_month SMALLINT[];
-- An earlier draft of this migration (never released) had one week_of_month.
ALTER TABLE admin_tasks DROP COLUMN IF EXISTS week_of_month;

ALTER TABLE admin_tasks DROP CONSTRAINT IF EXISTS admin_tasks_repeat_check;
ALTER TABLE admin_tasks DROP CONSTRAINT IF EXISTS admin_tasks_check;
ALTER TABLE admin_tasks DROP CONSTRAINT IF EXISTS admin_tasks_repeat_allowed;
ALTER TABLE admin_tasks DROP CONSTRAINT IF EXISTS admin_tasks_repeat_fields;
ALTER TABLE admin_tasks DROP CONSTRAINT IF EXISTS admin_tasks_interval_allowed;

UPDATE admin_tasks SET repeat = 'weekly', interval_count = 2, weekdays = ARRAY[(EXTRACT(ISODOW FROM first_date)::int - 1)::smallint]
  WHERE repeat = 'biweekly';
UPDATE admin_tasks SET weekdays = ARRAY[weekday] WHERE repeat = 'weekly' AND weekdays IS NULL AND weekday IS NOT NULL;
UPDATE admin_tasks SET repeat = 'monthly_day' WHERE repeat = 'monthly';
UPDATE admin_tasks SET first_date = created_at::date WHERE first_date IS NULL;

ALTER TABLE admin_tasks ADD CONSTRAINT admin_tasks_repeat_allowed
  CHECK (repeat IN ('weekly', 'monthly_day', 'monthly_weekday'));
ALTER TABLE admin_tasks ADD CONSTRAINT admin_tasks_interval_allowed CHECK (interval_count BETWEEN 1 AND 12);
ALTER TABLE admin_tasks ADD CONSTRAINT admin_tasks_repeat_fields CHECK (
  first_date IS NOT NULL AND (
    (repeat = 'weekly' AND cardinality(weekdays) > 0)
    OR (repeat = 'monthly_day' AND day_of_month IS NOT NULL)
    OR (repeat = 'monthly_weekday' AND cardinality(weekdays) > 0 AND cardinality(weeks_of_month) > 0)
  )
);
