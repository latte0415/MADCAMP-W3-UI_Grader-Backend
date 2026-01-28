-- 최근 10건의 run을 제외하고 전부 삭제하는 스크립트
-- 주의: 이 스크립트는 최근 10건을 제외한 모든 run과 관련 데이터를 삭제합니다.
-- 실행 전에 백업을 권장합니다.

-- 1. 삭제될 run 개수 확인 (실행 전 확인용)
SELECT 
    COUNT(*) as total_runs,
    COUNT(*) - 10 as runs_to_delete,
    10 as runs_to_keep
FROM runs;

-- 2. 삭제될 run 목록 확인 (실행 전 확인용)
SELECT 
    id,
    target_url,
    status,
    created_at
FROM runs
WHERE id NOT IN (
    SELECT id 
    FROM runs 
    ORDER BY created_at DESC 
    LIMIT 10
)
ORDER BY created_at DESC;

-- 3. 실제 삭제 실행
-- ON DELETE CASCADE로 인해 관련된 모든 데이터가 자동으로 삭제됩니다:
-- - nodes (runs.id ON DELETE CASCADE)
-- - edges (runs.id ON DELETE CASCADE)
-- - run_memory (runs.id ON DELETE CASCADE)
-- - pending_actions (runs.id ON DELETE CASCADE)
-- - site_evaluations (runs.id ON DELETE CASCADE)
-- - node_evaluations (site_evaluations.id ON DELETE CASCADE)
-- - edge_evaluations (site_evaluations.id ON DELETE CASCADE)
-- - workflow_evaluations (site_evaluations.id ON DELETE CASCADE)

DELETE FROM runs
WHERE id NOT IN (
    SELECT id 
    FROM runs 
    ORDER BY created_at DESC 
    LIMIT 10
);

-- 4. 삭제 후 확인
SELECT 
    COUNT(*) as remaining_runs,
    MIN(created_at) as oldest_run,
    MAX(created_at) as newest_run
FROM runs;
