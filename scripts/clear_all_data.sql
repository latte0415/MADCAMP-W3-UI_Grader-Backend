-- Clear Supabase storage objects and graph data
-- WARNING: This deletes ALL objects in the ui-artifacts bucket and ALL runs/nodes/edges rows.

BEGIN;

-- 1) Delete all storage files for UI artifacts
DELETE FROM storage.objects
WHERE bucket_id = 'ui-artifacts';

-- 2) Delete graph data (order not strictly required due to CASCADE)
TRUNCATE TABLE edges, nodes, runs RESTART IDENTITY;

COMMIT;
