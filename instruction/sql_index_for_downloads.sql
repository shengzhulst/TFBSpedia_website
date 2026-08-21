-- Indexes required by the CSV download endpoints
-- (/api/tfbs/download/ and /api/batch-tfbs/download/).
--
-- Looking up the regions bound by one TF means filtering "TFBS_name" on either
-- "TFBS" or "predicted_TFBS".  The pre-existing index
--
--     tfbs_name_idx btree ("TFBS", "predicted_TFBS")
--
-- cannot serve "predicted_TFBS" on its own (it is not the leading column), and
-- for "TFBS" it still has to visit the heap for every match because "ID" is not
-- in the index.  On a 200M+ row table that meant a full scan or ~1M random heap
-- reads per download, so a query such as ESR1 (1.1M regions) ran far past the
-- reverse proxy's timeout and returned "502 Proxy Error".
--
-- The two indexes below make each lookup an index-only scan that yields IDs
-- already in ID order, which is what lets the download stream rows out
-- immediately instead of sorting the whole result set first.
--
-- Run once against each database.  CONCURRENTLY keeps the table writable and
-- must not run inside a transaction block, so use psql -f (not BEGIN/COMMIT):
--
--     psql -U postgres -d tfbspedia_human -f instruction/sql_index_for_downloads.sql
--     psql -U postgres -d tfbspedia_mouse -f instruction/sql_index_for_downloads.sql
--
-- Measured on a local copy: the two indexes take about 6 minutes and 10 GB of
-- disk on the human database (226M rows) and under a minute and ~1 GB on mouse
-- (25M rows).  CONCURRENTLY scans the table twice, so allow more.  If a build
-- is interrupted it leaves an INVALID index behind; drop it
-- (DROP INDEX IF EXISTS <name>) and re-run.

SET maintenance_work_mem = '2GB';
SET max_parallel_maintenance_workers = 4;

CREATE INDEX CONCURRENTLY IF NOT EXISTS tfbs_name_tfbs_id_idx
    ON "TFBS_name" ("TFBS", "ID");

CREATE INDEX CONCURRENTLY IF NOT EXISTS tfbs_name_predicted_id_idx
    ON "TFBS_name" ("predicted_TFBS", "ID");

ANALYZE "TFBS_name";
