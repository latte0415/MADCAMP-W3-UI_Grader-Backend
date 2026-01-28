-- evaluation_result_json이 NULL인 run과 관련된 모든 데이터를 삭제하는 스크립트
-- 주의: 이 스크립트는 evaluation_result_json이 NULL인 모든 run과 관련 데이터를 삭제합니다.
-- 실행 전에 백업을 권장합니다.

-- 1. 삭제될 run 개수 확인 (실행 전 확인용)
SELECT 
    COUNT(*) as total_runs,
    COUNT(*) FILTER (WHERE evaluation_result_json IS NULL) as runs_without_evaluation,
    COUNT(*) FILTER (WHERE evaluation_result_json IS NOT NULL) as runs_with_evaluation
FROM runs;

-- 2. 삭제될 run 목록 확인 (실행 전 확인용)
SELECT 
    id,
    target_url,
    status,
    created_at,
    completed_at,
    CASE 
        WHEN evaluation_result_json IS NULL THEN 'NULL'
        ELSE 'HAS_DATA'
    END as evaluation_status
FROM runs
WHERE evaluation_result_json IS NULL
ORDER BY created_at DESC;

-- 3. 삭제될 run의 통계 정보 확인 (실행 전 확인용)
SELECT 
    status,
    COUNT(*) as count,
    MIN(created_at) as oldest_run,
    MAX(created_at) as newest_run
FROM runs
WHERE evaluation_result_json IS NULL
GROUP BY status
ORDER BY count DESC;

-- 4. 실제 삭제 실행
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
WHERE evaluation_result_json IS NULL;

-- 5. 삭제 후 확인
SELECT 
    COUNT(*) as remaining_runs,
    COUNT(*) FILTER (WHERE evaluation_result_json IS NULL) as runs_without_evaluation,
    COUNT(*) FILTER (WHERE evaluation_result_json IS NOT NULL) as runs_with_evaluation,
    MIN(created_at) as oldest_run,
    MAX(created_at) as newest_run
FROM runs;
