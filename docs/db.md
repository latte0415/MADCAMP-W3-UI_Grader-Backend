# Supabase DB 스키마

## runs 테이블
탐색 세션 정보를 저장하는 테이블

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_url TEXT NOT NULL,  -- 탐색 대상 웹사이트 URL
    start_url TEXT NOT NULL,  -- 시작 URL
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'stopped')),
    metadata JSONB,  -- 추가 메타데이터
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_created_at ON runs(created_at);
```

## nodes 테이블
화면(상태) 정보를 저장하는 테이블

**중요**: 같은 URL, 같은 DOM 구조라도 인증 상태나 스토리지 상태가 다르면 다른 노드로 봐야 합니다.

```sql
CREATE TABLE nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,

    url TEXT NOT NULL,
    url_normalized TEXT NOT NULL,  -- 정규화된 URL (쿼리 파라미터 정렬, 해시 제거 등)

    -- fingerprints (동치 판정용)
    a11y_hash VARCHAR(64) NOT NULL,  -- 접근성 정보 해시 (ARIA 속성, 역할 등)
    content_dom_hash VARCHAR(64),   -- 콘텐츠 DOM 해시 (선택적, 텍스트 콘텐츠 중심)
    state_hash VARCHAR(64) NOT NULL,  -- 상태 해시 (auth + storage 상태의 해시)

    -- 상태 요약 (원본 저장 금지)
    auth_state JSONB,  -- {is_logged_in: bool, user_role: str, plan: str, tenant: str, ...}
    storage_fingerprint JSONB,  -- {local_keys: [...], hashed_values: {k: sha256...}, ...}

    -- 원본 아티팩트 경로 (파일 저장소 참조)
    dom_snapshot_ref TEXT,  -- DOM 스냅샷 파일 경로
    a11y_snapshot_ref TEXT,  -- 접근성 스냅샷 파일 경로
    screenshot_ref TEXT,  -- 스크린샷 파일 경로
    storage_ref TEXT,  -- storageState 원본 파일 경로

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT nodes_unique_state UNIQUE (run_id, url_normalized, a11y_hash, state_hash)
);

-- 인덱스
CREATE INDEX idx_nodes_run_url ON nodes(run_id, url_normalized);
CREATE INDEX idx_nodes_run_state ON nodes(run_id, state_hash);
CREATE INDEX idx_nodes_auth_state ON nodes USING GIN (auth_state);
```

**주요 필드 설명:**
- `run_id`: 탐색 세션 구분
- `a11y_hash`: 접근성 정보 해시 (ARIA 속성, 역할, 이름 등) - UI 평가에 중요
- `content_dom_hash`: 콘텐츠 중심 DOM 해시 (선택적, 텍스트 콘텐츠가 중요한 경우)
- `state_hash`: 인증 + 스토리지 상태 해시
- `auth_state`: 인증 상태 요약 (원본 토큰 등은 저장하지 않음)
- `storage_fingerprint`: 스토리지 상태 지문 (키 목록 + 해시된 값, 민감 정보 보호)
- `*_ref`: 원본 데이터는 파일로 저장하고 경로만 참조 (DB 크기 관리)

## edges 테이블
화면 간 전환(액션) 정보를 저장하는 테이블

```sql
CREATE TABLE edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,

    from_node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    to_node_id UUID REFERENCES nodes(id) ON DELETE SET NULL,  -- 실패 케이스도 기록 가능 (NULL 허용)

    action_type VARCHAR(20) NOT NULL CHECK (action_type IN ('click', 'fill', 'navigate', 'scroll', 'keyboard', 'wait')),
    action_target TEXT NOT NULL,  -- 가능하면 selector보다 role+name 같이 저장 (예: "button[name='로그인']")
    action_value TEXT,  -- 입력 값 (fill 액션의 경우)

    cost NUMERIC NOT NULL DEFAULT 1,  -- 액션 비용 (Interaction Efficiency 평가용)
    latency_ms INT,  -- action 수행~안정화까지 소요 시간 (System Latency 평가용)
    outcome VARCHAR(20) NOT NULL DEFAULT 'success' CHECK (outcome IN ('success', 'fail', 'timeout', 'blocked')),
    error_msg TEXT,  -- 실패 시 에러 메시지 (Error reporting 평가용)

    intent_label TEXT,  -- LLM 라벨 (정형값 추천, 예: "login", "submit_form", "navigate_to_dashboard")
    intent_confidence NUMERIC,  -- 의도 파악 신뢰도 (0.0 ~ 1.0)

    dom_diff_ref TEXT,  -- DOM 변화 diff 파일 경로
    network_summary_ref TEXT,  -- 네트워크 요약 정보 파일 경로

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT edges_dedupe UNIQUE (
        run_id, from_node_id, to_node_id, action_type, action_target, COALESCE(action_value, '')
    )
);

-- 인덱스
CREATE INDEX idx_edges_run_from ON edges(run_id, from_node_id);
CREATE INDEX idx_edges_run_to ON edges(run_id, to_node_id);
CREATE INDEX idx_edges_run_type ON edges(run_id, action_type);
CREATE INDEX idx_edges_outcome ON edges(outcome);
CREATE INDEX idx_edges_cost ON edges(cost);
```

**주요 필드 설명:**
- `run_id`: 탐색 세션 구분
- `to_node_id`: NULL 허용 (실패 케이스도 기록 가능)
- `action_target`: selector보다 role+name 우선 (접근성 고려)
- `cost`: 액션 비용 (Interaction Efficiency 평가)
- `latency_ms`: 응답 시간 (System Latency & Responsiveness 평가)
- `outcome`: 성공/실패 여부 (Error reporting 평가)
- `error_msg`: 에러 메시지 (Error reporting, diagnosis 평가)
- `intent_label`: LLM이 파악한 액션 의도 (Clarity & Affordance 평가)
- `*_ref`: 원본 데이터는 파일로 저장하고 경로만 참조

## 사용 예시

### 특정 화면(상태)에서 가능한 액션 조회
```sql
SELECT 
    e.action_type,
    e.action_target,
    e.action_value,
    e.cost,
    e.outcome,
    n_to.url AS target_url,
    n_to.auth_state->>'is_logged_in' AS target_is_logged_in
FROM edges e
JOIN nodes n_from ON e.from_node_id = n_from.id
LEFT JOIN nodes n_to ON e.to_node_id = n_to.id
WHERE n_from.run_id = $run_id
  AND n_from.url = 'https://example.com/login'
  AND n_from.state_hash = 'abc123...';  -- 특정 상태의 노드
```

### 로그인 상태인 특정 화면으로 가는 경로 찾기
```sql
SELECT 
    n_from.url AS from_url,
    n_from.auth_state->>'is_logged_in' AS from_is_logged_in,
    e.action_type,
    e.action_target,
    e.cost,
    e.latency_ms,
    n_to.url AS to_url
FROM edges e
JOIN nodes n_from ON e.from_node_id = n_from.id
JOIN nodes n_to ON e.to_node_id = n_to.id
WHERE e.run_id = $run_id
  AND n_to.url = 'https://example.com/dashboard'
  AND n_to.auth_state->>'is_logged_in' = 'true'
  AND e.outcome = 'success'
ORDER BY e.cost;  -- 최소 비용 경로 우선
```

### 동일 URL이지만 다른 상태인 노드 찾기
```sql
SELECT 
    id,
    url,
    state_hash,
    a11y_hash,
    auth_state->>'is_logged_in' AS is_logged_in,
    storage_fingerprint
FROM nodes
WHERE run_id = $run_id
  AND url_normalized = 'https://example.com/dashboard'
ORDER BY created_at;
```

### 노드 동치 판단 (같은 화면+상태인지 확인)
```sql
-- 새로 발견한 상태와 기존 노드 비교
SELECT id, url, state_hash, a11y_hash
FROM nodes
WHERE run_id = $run_id
  AND url_normalized = $url_normalized
  AND a11y_hash = $a11y_hash
  AND state_hash = $state_hash;  -- auth_state + storage_fingerprint의 해시
```

### 실패한 액션 조회 (Error reporting 평가용)
```sql
SELECT 
    e.action_type,
    e.action_target,
    e.error_msg,
    e.outcome,
    n_from.url AS from_url
FROM edges e
JOIN nodes n_from ON e.from_node_id = n_from.id
WHERE e.run_id = $run_id
  AND e.outcome != 'success'
ORDER BY e.created_at;
```

### 평균 응답 시간 조회 (System Latency 평가용)
```sql
SELECT 
    action_type,
    AVG(latency_ms) AS avg_latency,
    COUNT(*) AS total_count
FROM edges
WHERE run_id = $run_id
  AND outcome = 'success'
  AND latency_ms IS NOT NULL
GROUP BY action_type
ORDER BY avg_latency DESC;
```

## 해시 생성 방법

### state_hash 생성

`state_hash`는 인증 상태와 스토리지 지문을 합쳐서 생성하는 해시값입니다.

```python
import hashlib
import json

def generate_state_hash(auth_state: dict, storage_fingerprint: dict) -> str:
    """인증 상태와 스토리지 지문을 합쳐서 해시 생성"""
    # 상태를 정규화 (키 정렬)
    normalized_auth = json.dumps(auth_state, sort_keys=True)
    normalized_storage = json.dumps(storage_fingerprint, sort_keys=True)
    
    # 합쳐서 해시
    combined = f"{normalized_auth}|{normalized_storage}"
    return hashlib.sha256(combined.encode()).hexdigest()
```

### storage_fingerprint 생성

민감한 정보를 보호하면서 스토리지 상태를 식별할 수 있는 지문을 생성합니다.

```python
def generate_storage_fingerprint(local_storage: dict, session_storage: dict) -> dict:
    """스토리지 상태 지문 생성 (민감 정보 보호)"""
    fingerprint = {
        "local_keys": sorted(local_storage.keys()),
        "session_keys": sorted(session_storage.keys()),
        "hashed_values": {}
    }
    
    # 값의 해시만 저장 (원본 값은 저장하지 않음)
    for key in local_storage.keys():
        value = str(local_storage[key])
        fingerprint["hashed_values"][f"local_{key}"] = hashlib.sha256(value.encode()).hexdigest()
    
    for key in session_storage.keys():
        value = str(session_storage[key])
        fingerprint["hashed_values"][f"session_{key}"] = hashlib.sha256(value.encode()).hexdigest()
    
    return fingerprint

# 예시
local_storage = {"theme": "dark", "userId": "12345"}
session_storage = {"sessionId": "abc123"}
storage_fingerprint = generate_storage_fingerprint(local_storage, session_storage)
# 결과: {
#   "local_keys": ["theme", "userId"],
#   "session_keys": ["sessionId"],
#   "hashed_values": {
#     "local_theme": "sha256...",
#     "local_userId": "sha256...",
#     "session_sessionId": "sha256..."
#   }
# }
```

### a11y_hash 생성

접근성 정보를 기반으로 해시를 생성합니다.

```python
def generate_a11y_hash(page) -> str:
    """접근성 정보 기반 해시 생성"""
    a11y_info = []
    
    # ARIA 속성, 역할, 이름 등 접근성 정보 수집
    for element in page.query_selector_all("[role], [aria-label], [aria-labelledby]"):
        role = element.get_attribute("role")
        label = element.get_attribute("aria-label")
        name = element.inner_text().strip()[:50]  # 처음 50자만
        a11y_info.append(f"{role}|{label}|{name}")
    
    # 정렬 후 해시
    normalized = "|".join(sorted(a11y_info))
    return hashlib.sha256(normalized.encode()).hexdigest()
```

**주의사항:**
- 민감한 정보(토큰 값 등)는 해시 생성 시 제외하거나 마스킹
- 같은 상태는 항상 같은 해시가 나와야 함 (키 정렬 필수)
- 원본 데이터는 파일로 저장하고 DB에는 경로만 저장

## Supabase 설정 참고사항

1. **RLS (Row Level Security)**: 필요시 활성화
2. **자동 생성 UUID**: `gen_random_uuid()` 사용 (Supabase 기본)
3. **타임스탬프**: `TIMESTAMPTZ` 사용 (Supabase 권장)
4. **외래키**: `ON DELETE CASCADE`로 노드 삭제 시 관련 엣지 자동 삭제
5. **JSONB 인덱스**: `USING GIN`으로 JSONB 필드 인덱싱 (쿼리 성능 향상)