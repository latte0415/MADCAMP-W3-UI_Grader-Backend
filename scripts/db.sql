-- Supabase DB 스키마
-- 실행 순서: runs -> nodes -> edges

-- ============================================
-- 1. runs 테이블
-- ============================================
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_url TEXT NOT NULL,
    start_url TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'stopped')),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_created_at ON runs(created_at);

-- ============================================
-- 2. nodes 테이블
-- ============================================
CREATE TABLE nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,

    url TEXT NOT NULL,
    url_normalized TEXT NOT NULL,

    -- fingerprints (동치 판정용)
    a11y_hash VARCHAR(64) NOT NULL,
    content_dom_hash VARCHAR(64),
    state_hash VARCHAR(64) NOT NULL,

    -- 상태 요약 (원본 저장 금지)
    auth_state JSONB,
    storage_fingerprint JSONB,

    -- 원본 아티팩트 경로 (파일 저장소 참조)
    dom_snapshot_ref TEXT,
    a11y_snapshot_ref TEXT,
    screenshot_ref TEXT,
    storage_ref TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT nodes_unique_state UNIQUE (run_id, url_normalized, a11y_hash, state_hash)
);

-- nodes 인덱스
CREATE INDEX idx_nodes_run_url ON nodes(run_id, url_normalized);
CREATE INDEX idx_nodes_run_state ON nodes(run_id, state_hash);
CREATE INDEX idx_nodes_a11y_hash ON nodes(a11y_hash);
CREATE INDEX idx_nodes_state_hash ON nodes(state_hash);
CREATE INDEX idx_nodes_auth_state ON nodes USING GIN (auth_state);

-- ============================================
-- 3. edges 테이블
-- ============================================
CREATE TABLE edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,

    from_node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    to_node_id UUID REFERENCES nodes(id) ON DELETE SET NULL,

    action_type VARCHAR(20) NOT NULL CHECK (action_type IN ('click', 'fill', 'navigate', 'scroll', 'keyboard', 'wait')),
    action_target TEXT NOT NULL,
    action_value TEXT DEFAULT '',

    cost NUMERIC NOT NULL DEFAULT 1,
    latency_ms INT,
    outcome VARCHAR(20) NOT NULL DEFAULT 'success' CHECK (outcome IN ('success', 'fail', 'timeout', 'blocked')),
    error_msg TEXT,

    intent_label TEXT,
    intent_confidence NUMERIC,

    dom_diff_ref TEXT,
    network_summary_ref TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT edges_dedupe UNIQUE (
        run_id, from_node_id, to_node_id, action_type, action_target, action_value
    )
);

-- edges 인덱스
CREATE INDEX idx_edges_run_from ON edges(run_id, from_node_id);
CREATE INDEX idx_edges_run_to ON edges(run_id, to_node_id);
CREATE INDEX idx_edges_run_type ON edges(run_id, action_type);
CREATE INDEX idx_edges_outcome ON edges(outcome);
CREATE INDEX idx_edges_cost ON edges(cost);
CREATE INDEX idx_edges_from_node ON edges(from_node_id);
CREATE INDEX idx_edges_to_node ON edges(to_node_id);
CREATE INDEX idx_edges_action_type ON edges(action_type);
