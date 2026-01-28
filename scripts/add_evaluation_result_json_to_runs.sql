-- Migration: Add evaluation_result_json column to runs table
-- 이 마이그레이션은 runs 테이블에 evaluation_result_json JSONB 컬럼을 추가합니다.
-- 평가 완료된 전체 JSON 결과를 저장하기 위한 컬럼입니다.

-- ============================================
-- 1. evaluation_result_json 컬럼 추가 (JSONB 타입)
-- ============================================
ALTER TABLE runs
    ADD COLUMN IF NOT EXISTS evaluation_result_json JSONB;

-- ============================================
-- 2. (선택사항) 인덱스 생성 (JSONB 쿼리 성능 향상)
-- ============================================
-- JSONB 필드에 대한 GIN 인덱스는 JSON 쿼리 성능을 향상시킵니다.
-- 하지만 저장만 하고 조회를 자주 하지 않는다면 인덱스는 선택사항입니다.
-- CREATE INDEX IF NOT EXISTS idx_runs_evaluation_result_json ON runs USING GIN (evaluation_result_json);

-- ============================================
-- 3. 마이그레이션 완료 확인 쿼리
-- ============================================
-- 다음 쿼리로 마이그레이션 결과를 확인할 수 있습니다:
-- SELECT 
--     COUNT(*) as total_runs,
--     COUNT(evaluation_result_json) as runs_with_evaluation_json,
--     COUNT(*) - COUNT(evaluation_result_json) as runs_without_evaluation_json
-- FROM runs;
