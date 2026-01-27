-- 사이트 평가 결과 저장을 위한 DB 스키마
-- 기존 runs, nodes, edges 테이블과 연계

-- ============================================
-- 1. site_evaluations 테이블
-- 전체 평가 결과 요약 정보 저장
-- ============================================
CREATE TABLE IF NOT EXISTS site_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    
    -- 평가 메타데이터
    timestamp TIMESTAMPTZ NOT NULL,
    total_score NUMERIC NOT NULL CHECK (total_score >= 0 AND total_score <= 100),
    
    -- 카테고리별 점수
    learnability_score NUMERIC NOT NULL CHECK (learnability_score >= 0 AND learnability_score <= 100),
    efficiency_score NUMERIC NOT NULL CHECK (efficiency_score >= 0 AND efficiency_score <= 100),
    control_score NUMERIC NOT NULL CHECK (control_score >= 0 AND control_score <= 100),
    
    -- 요약 정보
    node_count INT NOT NULL DEFAULT 0,
    edge_count INT NOT NULL DEFAULT 0,
    path_count INT NOT NULL DEFAULT 0,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT site_evaluations_run_unique UNIQUE (run_id)
);

CREATE INDEX idx_site_evaluations_run_id ON site_evaluations(run_id);
CREATE INDEX idx_site_evaluations_timestamp ON site_evaluations(timestamp);
CREATE INDEX idx_site_evaluations_total_score ON site_evaluations(total_score);

-- ============================================
-- 2. node_evaluations 테이블
-- 노드별 정적 분석 결과 저장
-- ============================================
CREATE TABLE IF NOT EXISTS node_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_evaluation_id UUID NOT NULL REFERENCES site_evaluations(id) ON DELETE CASCADE,
    node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    
    url TEXT NOT NULL,
    
    -- 카테고리별 점수
    learnability_score NUMERIC NOT NULL CHECK (learnability_score >= 0 AND learnability_score <= 100),
    efficiency_score NUMERIC NOT NULL CHECK (efficiency_score >= 0 AND efficiency_score <= 100),
    control_score NUMERIC NOT NULL CHECK (control_score >= 0 AND control_score <= 100),
    
    -- 상세 평가 항목 (JSONB로 저장)
    learnability_items JSONB DEFAULT '[]'::jsonb,
    efficiency_items JSONB DEFAULT '[]'::jsonb,
    control_items JSONB DEFAULT '[]'::jsonb,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT node_evaluations_unique UNIQUE (site_evaluation_id, node_id)
);

CREATE INDEX idx_node_evaluations_site_eval ON node_evaluations(site_evaluation_id);
CREATE INDEX idx_node_evaluations_node_id ON node_evaluations(node_id);
CREATE INDEX idx_node_evaluations_url ON node_evaluations(url);
CREATE INDEX idx_node_evaluations_learnability ON node_evaluations(learnability_score);
CREATE INDEX idx_node_evaluations_efficiency ON node_evaluations(efficiency_score);
CREATE INDEX idx_node_evaluations_control ON node_evaluations(control_score);
CREATE INDEX idx_node_evaluations_items ON node_evaluations USING GIN (learnability_items, efficiency_items, control_items);

-- ============================================
-- 3. edge_evaluations 테이블
-- 엣지별 전환 분석 결과 저장
-- ============================================
CREATE TABLE IF NOT EXISTS edge_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_evaluation_id UUID NOT NULL REFERENCES site_evaluations(id) ON DELETE CASCADE,
    edge_id UUID NOT NULL REFERENCES edges(id) ON DELETE CASCADE,
    
    action TEXT NOT NULL,
    
    -- 카테고리별 점수
    learnability_score NUMERIC NOT NULL CHECK (learnability_score >= 0 AND learnability_score <= 100),
    efficiency_score NUMERIC NOT NULL CHECK (efficiency_score >= 0 AND efficiency_score <= 100),
    control_score NUMERIC NOT NULL CHECK (control_score >= 0 AND control_score <= 100),
    
    -- 지연 시간 정보 (efficiency 카테고리에서)
    latency_duration_ms INT,
    latency_status VARCHAR(20),  -- 'Excellent', 'Good', 'Slow', etc.
    latency_description TEXT,
    
    -- 상세 평가 항목 (JSONB로 저장)
    learnability_passed JSONB DEFAULT '[]'::jsonb,
    learnability_failed JSONB DEFAULT '[]'::jsonb,
    efficiency_passed JSONB DEFAULT '[]'::jsonb,
    efficiency_failed JSONB DEFAULT '[]'::jsonb,
    control_passed JSONB DEFAULT '[]'::jsonb,
    control_failed JSONB DEFAULT '[]'::jsonb,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT edge_evaluations_unique UNIQUE (site_evaluation_id, edge_id)
);

CREATE INDEX idx_edge_evaluations_site_eval ON edge_evaluations(site_evaluation_id);
CREATE INDEX idx_edge_evaluations_edge_id ON edge_evaluations(edge_id);
CREATE INDEX idx_edge_evaluations_action ON edge_evaluations(action);
CREATE INDEX idx_edge_evaluations_learnability ON edge_evaluations(learnability_score);
CREATE INDEX idx_edge_evaluations_efficiency ON edge_evaluations(efficiency_score);
CREATE INDEX idx_edge_evaluations_control ON edge_evaluations(control_score);
CREATE INDEX idx_edge_evaluations_latency ON edge_evaluations(latency_duration_ms);
CREATE INDEX idx_edge_evaluations_latency_status ON edge_evaluations(latency_status);

-- ============================================
-- 4. workflow_evaluations 테이블 (향후 확장용)
-- 워크플로우 분석 결과 저장
-- ============================================
CREATE TABLE IF NOT EXISTS workflow_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_evaluation_id UUID NOT NULL REFERENCES site_evaluations(id) ON DELETE CASCADE,
    
    -- 워크플로우 정보 (향후 확장 시 사용)
    workflow_data JSONB DEFAULT '{}'::jsonb,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_workflow_evaluations_site_eval ON workflow_evaluations(site_evaluation_id);
CREATE INDEX idx_workflow_evaluations_data ON workflow_evaluations USING GIN (workflow_data);
