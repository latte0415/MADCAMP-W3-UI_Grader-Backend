-- Migration: Add user_id column to runs table
-- 이 마이그레이션은 runs 테이블에 user_id 컬럼을 추가하고,
-- 기존 metadata JSONB 필드에 저장된 user_id를 새 컬럼으로 마이그레이션합니다.

-- ============================================
-- 1. user_id 컬럼 추가 (nullable, 나중에 NOT NULL로 변경)
-- ============================================
ALTER TABLE runs
    ADD COLUMN IF NOT EXISTS user_id UUID;

-- ============================================
-- 2. 기존 metadata에서 user_id 추출하여 새 컬럼에 저장
-- ============================================
UPDATE runs
SET user_id = (metadata->>'user_id')::UUID
WHERE metadata->>'user_id' IS NOT NULL
  AND user_id IS NULL;

-- ============================================
-- 3. user_id 인덱스 생성 (쿼리 성능 향상)
-- ============================================
CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_user_id_created_at ON runs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_user_id_status ON runs(user_id, status);

-- ============================================
-- 4. (선택사항) user_id를 NOT NULL로 변경하려면 아래 주석 해제
-- 주의: 모든 기존 데이터에 user_id가 있는 경우에만 실행하세요
-- ============================================
-- ALTER TABLE runs
--     ALTER COLUMN user_id SET NOT NULL;

-- ============================================
-- 5. 마이그레이션 완료 확인 쿼리
-- ============================================
-- 다음 쿼리로 마이그레이션 결과를 확인할 수 있습니다:
-- SELECT 
--     COUNT(*) as total_runs,
--     COUNT(user_id) as runs_with_user_id,
--     COUNT(*) - COUNT(user_id) as runs_without_user_id
-- FROM runs;
