-- Hiring-status support for the Industry Console.
--
-- applications.status already carries the recruitment lifecycle:
--   applied -> shortlisted -> selected | rejected (withdrawn = student opt-out).
-- 'waitlisted' is the only missing state the console needs, so we extend the
-- existing check constraint. Single authoritative status field -- no boolean
-- flags like is_hired/is_waitlisted/is_rejected. applied_at/updated_at already
-- cover the timeline the console displays.

alter table applications
    drop constraint if exists applications_status_check;

alter table applications
    add constraint applications_status_check
    check (status in ('applied', 'shortlisted', 'waitlisted', 'selected', 'rejected', 'withdrawn'));
