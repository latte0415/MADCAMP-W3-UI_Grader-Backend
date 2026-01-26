-- Run Memory 테이블 생성
-- 런 사이클 내 자연어 메모리를 저장하는 테이블

CREATE TABLE IF NOT EXISTS run_memory (
    run_id UUID PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- run_id는 PRIMARY KEY로 자동 유니크 제약이 적용됨
-- 인덱스는 PRIMARY KEY로 자동 생성됨

-- content JSONB 필드에 대한 GIN 인덱스 (JSONB 쿼리 성능 향상)
CREATE INDEX IF NOT EXISTS idx_run_memory_content ON run_memory USING GIN (content);

-- updated_at 자동 업데이트 트리거 함수
CREATE OR REPLACE FUNCTION update_run_memory_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- updated_at 자동 업데이트 트리거
CREATE TRIGGER trigger_update_run_memory_updated_at
    BEFORE UPDATE ON run_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_run_memory_updated_at();
