# 백엔드 API 스펙 문서

프론트엔드 모니터링 페이지가 요구하는 백엔드 API 엔드포인트 및 응답 형식입니다.

## 필수 API 엔드포인트

### 1. `GET /api/runs/{run_id}/monitor`

Run 모니터링 데이터를 조회합니다.

#### 응답 형식

```json
{
  "run_info": {
    "run_id": "string",
    "status": "running" | "completed" | "failed" | "stopped",
    "target_url": "string",
    "start_url": "string",
    "created_at": "ISO 8601 datetime string",
    "completed_at": "ISO 8601 datetime string | null",
    "execution_time": "number (seconds)"
  },
  "statistics": {
    "node_count": "number",
    "edge_count": "number",
    "action_type_distribution": {
      "click": "number",
      "fill": "number",
      "navigate": "number",
      ...
    },
    "edge_outcomes": {
      "success": "number",
      "fail": "number",
      "total": "number"
    }
  },
  "pending_actions": {
    "count": "number",
    "actions": [
      {
        "type": "string (action type)",
        "action_type": "string (alternative field name)",
        ... // 기타 액션 관련 필드들
      },
      ...
    ]
    // 또는
    "list": [...] // actions 대신 list 필드명도 지원
  },
  "run_memory": {
    "key_count": "number",
    "memory": {
      "key1": "value1",
      "key2": {
        "nested": "object"
      },
      ...
    }
    // 또는
    "data": {...}, // memory 대신 data 필드명도 지원
    // 또는 직접 객체 형태로도 지원
    "key1": "value1",
    "key2": {...}
  }
}
```

#### 중요 사항

- **pending_actions**: 
  - `count` 필드는 필수입니다 (통계 카드에 표시)
  - `actions` 또는 `list` 배열에 각 pending action의 상세 정보가 포함되어야 합니다
  - 각 action 객체는 최소한 `type` 또는 `action_type` 필드를 포함해야 합니다
  - 전체 action 객체는 JSON으로 표시되므로 모든 관련 필드를 포함하는 것이 좋습니다

- **run_memory**:
  - `key_count` 필드는 선택사항입니다 (없으면 `memory` 또는 `data` 객체의 키 개수로 계산)
  - `memory` 또는 `data` 필드에 키-값 쌍이 포함되어야 합니다
  - 값은 문자열, 숫자, 객체 등 어떤 형태든 가능합니다 (JSON으로 표시됨)

### 2. `GET /api/runs/{run_id}/graph`

그래프 구조 데이터를 조회합니다.

#### 응답 형식

```json
{
  "nodes": [
    {
      "id": "string",
      "url": "string",
      "label": "string (optional)",
      ...
    },
    ...
  ],
  "edges": [
    {
      "id": "string",
      "source": "string (node id)",
      "target": "string (node id)",
      "action_type": "string",
      "success": "boolean",
      ...
    },
    ...
  ]
}
```

### 3. `GET /api/workers/status`

전체 워커 상태를 조회합니다.

#### 응답 형식

```json
{
  "total": {
    "waiting": "number",
    "delayed": "number",
    "processing": "number"
  },
  "by_type": {
    "process_node_worker": {
      "waiting": "number",
      "delayed": "number",
      "processing": "number"
    },
    "process_action_worker": {
      "waiting": "number",
      "delayed": "number",
      "processing": "number"
    },
    "process_pending_actions_worker": {
      "waiting": "number",
      "delayed": "number",
      "processing": "number"
    }
  }
}
```

### 4. `GET /api/workers/status/{run_id}`

특정 run_id와 관련된 워커 상태를 조회합니다.

#### 응답 형식

```json
{
  "related_workers_count": "number",
  "workers": [
    {
      "worker_id": "string",
      "worker_type": "string",
      "status": "string",
      "run_id": "string",
      ...
    },
    ...
  ]
}
```

## Runs API 엔드포인트

### 5. `GET /api/runs`

사용자별 평가 요청(runs) 리스트를 조회합니다.

#### 요청
- 인증: Supabase JWT 토큰을 `Authorization` 헤더에 포함
  ```
  Authorization: Bearer {supabase_jwt_token}
  ```
- 쿼리 파라미터 (선택):
  - `limit` (optional): 반환할 항목 수 (기본값: 50, 최소: 1, 최대: 100)
  - `offset` (optional): 페이지네이션 오프셋 (기본값: 0)
  - `status` (optional): 상태 필터 (`running` | `completed` | `failed` | `stopped`)
  - `order_by` (optional): 정렬 기준 (기본값: `created_at`, 가능한 값: `created_at`, `completed_at`, `status`)
  - `order` (optional): 정렬 방향 (`asc` | `desc`, 기본값: `desc`)

#### 응답 형식

```json
{
  "runs": [
    {
      "run_id": "string (UUID)",
      "status": "running" | "completed" | "failed" | "stopped",
      "target_url": "string",
      "start_url": "string",
      "created_at": "ISO 8601 datetime string",
      "completed_at": "ISO 8601 datetime string | null",
      "execution_time": "number (seconds) | null",
      "evaluation": {
        "id": "string (UUID)",
        "total_score": "number (0-100)",
        "learnability_score": "number (0-100)",
        "efficiency_score": "number (0-100)",
        "control_score": "number (0-100)",
        "created_at": "ISO 8601 datetime string"
      } | null
    },
    ...
  ],
  "total": "number",
  "limit": "number",
  "offset": "number"
}
```

#### 응답 예시

```json
{
  "runs": [
    {
      "run_id": "667d1815-7718-40fc-bd95-c98101a11ac5",
      "status": "running",
      "target_url": "http://localhost:5174/dashboard",
      "start_url": "http://localhost:5174/dashboard",
      "created_at": "2026-01-27T17:36:35.344603+00:00",
      "completed_at": null,
      "execution_time": null,
      "evaluation": null
    },
    {
      "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "status": "completed",
      "target_url": "http://example.com",
      "start_url": "http://example.com",
      "created_at": "2026-01-27T16:00:00.000000+00:00",
      "completed_at": "2026-01-27T16:15:30.000000+00:00",
      "execution_time": 930,
      "evaluation": {
        "id": "eval-123",
        "total_score": 55.9,
        "learnability_score": 66.2,
        "efficiency_score": 48.5,
        "control_score": 52.9,
        "created_at": "2026-01-27T16:15:30.000000+00:00"
      }
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

#### HTTP 상태 코드
- `200 OK`: 성공
- `400 Bad Request`: 잘못된 쿼리 파라미터
- `401 Unauthorized`: 인증 토큰이 없거나 유효하지 않음
- `500 Internal Server Error`: 서버 오류

#### 구현 요구사항
1. 인증: Supabase JWT 토큰에서 `user_id` 추출
2. 필터링: `runs` 테이블의 `metadata->>user_id`로 해당 사용자의 runs만 조회
3. 조인: `status`가 `completed`인 경우 `site_evaluations`와 조인하여 평가 정보 포함
4. 정렬: 기본적으로 `created_at` 내림차순
5. execution_time: `completed_at`과 `created_at`의 차이를 초 단위로 계산 (완료된 경우만)

## 사이트 평가 API 엔드포인트

### 6. `GET /api/evaluation/validate`

특정 URL이 분석 가능한지(유효한지) 확인합니다.

#### 요청 파라미터

- `url` (query parameter, required): 분석할 대상 URL

#### 응답 형식

```json
{
  "valid": "boolean",
  "url": "string",
  "message": "string",
  "details": {
    "accessible": "boolean",
    "status_code": "number | null",
    "error": "string | null"
  }
}
```

#### 응답 예시

**유효한 URL:**
```json
{
  "valid": true,
  "url": "http://localhost:5174/dashboard",
  "message": "URL이 분석 가능합니다.",
  "details": {
    "accessible": true,
    "status_code": 200,
    "error": null
  }
}
```

**유효하지 않은 URL:**
```json
{
  "valid": false,
  "url": "http://invalid-url.example.com",
  "message": "URL에 접근할 수 없습니다.",
  "details": {
    "accessible": false,
    "status_code": null,
    "error": "Connection timeout"
  }
}
```

#### HTTP 상태 코드

- `200 OK`: 유효성 검사 완료 (valid 필드로 결과 확인)
- `400 Bad Request`: URL 파라미터가 없거나 형식이 잘못됨
- `500 Internal Server Error`: 서버 오류

### 7. `GET /api/evaluation/list`

사용자별 평가 리스트를 조회합니다. (완료된 평가만 반환)

#### 요청
- 인증: Supabase JWT 토큰을 `Authorization` 헤더에 포함
- 쿼리 파라미터 (선택):
  - `limit` (optional): 반환할 항목 수 (기본값: 50)
  - `offset` (optional): 페이지네이션 오프셋 (기본값: 0)
  - `order_by` (optional): 정렬 기준 (기본값: `created_at`)
  - `order` (optional): 정렬 방향 (`asc` | `desc`, 기본값: `desc`)

#### 응답 형식

```json
{
  "evaluations": [
    {
      "id": "string (UUID)",
      "run_id": "string (UUID)",
      "target_url": "string",
      "total_score": "number (0-100)",
      "learnability_score": "number (0-100)",
      "efficiency_score": "number (0-100)",
      "control_score": "number (0-100)",
      "created_at": "ISO 8601 datetime string",
      "timestamp": "ISO 8601 datetime string",
      "status": "completed"
    },
    ...
  ],
  "total": "number",
  "limit": "number",
  "offset": "number"
}
```

#### HTTP 상태 코드
- `200 OK`: 성공
- `401 Unauthorized`: 인증 토큰이 없거나 유효하지 않음
- `500 Internal Server Error`: 서버 오류

### 8. `POST /api/evaluation/analyze`

특정 URL에 대한 사이트 평가 분석을 시작합니다.

#### 요청
- 인증: Supabase JWT 토큰을 `Authorization` 헤더에 포함
  ```
  Authorization: Bearer {supabase_jwt_token}
  ```
- 요청 본문:

```json
{
  "url": "string (required)",
  "start_url": "string (optional, 기본값: url과 동일)",
  "metadata": {
    "key": "value"
  }
}
```

#### 응답 형식

```json
{
  "run_id": "string (UUID)",
  "status": "running",
  "target_url": "string",
  "start_url": "string",
  "created_at": "ISO 8601 datetime string",
  "message": "분석이 시작되었습니다."
}
```

#### 응답 예시

```json
{
  "run_id": "667d1815-7718-40fc-bd95-c98101a11ac5",
  "status": "running",
  "target_url": "http://localhost:5174/dashboard",
  "start_url": "http://localhost:5174/dashboard",
  "created_at": "2026-01-27T17:36:35.344603+00:00",
  "message": "분석이 시작되었습니다."
}
```

#### HTTP 상태 코드

- `201 Created`: 분석 작업이 성공적으로 시작됨
- `400 Bad Request`: 요청 데이터가 유효하지 않음 (URL이 없거나 형식이 잘못됨)
- `401 Unauthorized`: 인증 토큰이 없거나 유효하지 않음
- `422 Unprocessable Entity`: URL에 접근할 수 없거나 분석할 수 없음
- `500 Internal Server Error`: 서버 오류

#### 중요 사항

- 분석은 비동기로 실행되며, 완료까지 시간이 걸릴 수 있습니다.
- 분석 진행 상황은 `/api/runs/{run_id}/monitor` 엔드포인트로 확인할 수 있습니다.
- 분석이 완료되면 `/api/evaluation/{run_id}` 엔드포인트로 결과를 조회할 수 있습니다.

### 9. `GET /api/evaluation/{run_id}`

특정 run_id의 사이트 평가 결과를 조회합니다.

#### 경로 파라미터

- `run_id` (required): 평가 실행 ID (UUID)

#### 쿼리 파라미터

- `include_details` (optional, default: `true`): 상세 정보 포함 여부 (`true` | `false`)

#### 응답 형식

**include_details=true (기본값):**

```json
{
  "id": "string (UUID)",
  "run_id": "string (UUID)",
  "timestamp": "ISO 8601 datetime string",
  "total_score": "number (0-100)",
  "learnability_score": "number (0-100)",
  "efficiency_score": "number (0-100)",
  "control_score": "number (0-100)",
  "node_count": "number",
  "edge_count": "number",
  "path_count": "number",
  "created_at": "ISO 8601 datetime string",
  "node_evaluations": [
    {
      "id": "string (UUID)",
      "site_evaluation_id": "string (UUID)",
      "node_id": "string (UUID)",
      "url": "string",
      "learnability_score": "number (0-100)",
      "efficiency_score": "number (0-100)",
      "control_score": "number (0-100)",
      "learnability_items": [
        {
          "element": {
            "tag": "string",
            "text": "string",
            "id": "string",
            "class": "string",
            "type": "string"
          },
          "checks": [
            {
              "name": "string",
              "status": "PASS" | "FAIL",
              "message": "string"
            }
          ]
        }
      ],
      "efficiency_items": "array",
      "control_items": "array"
    }
  ],
  "edge_evaluations": [
    {
      "id": "string (UUID)",
      "site_evaluation_id": "string (UUID)",
      "edge_id": "string (UUID)",
      "action": "string",
      "learnability_score": "number (0-100)",
      "efficiency_score": "number (0-100)",
      "control_score": "number (0-100)",
      "latency_duration_ms": "number | null",
      "latency_status": "string | null",
      "latency_description": "string | null",
      "learnability_passed": "array",
      "learnability_failed": "array",
      "efficiency_passed": "array",
      "efficiency_failed": "array",
      "control_passed": "array",
      "control_failed": "array"
    }
  ],
  "workflow_evaluations": [
    {
      "id": "string (UUID)",
      "site_evaluation_id": "string (UUID)",
      "workflow_data": "object"
    }
  ]
}
```

**include_details=false:**

```json
{
  "id": "string (UUID)",
  "run_id": "string (UUID)",
  "timestamp": "ISO 8601 datetime string",
  "total_score": "number (0-100)",
  "learnability_score": "number (0-100)",
  "efficiency_score": "number (0-100)",
  "control_score": "number (0-100)",
  "node_count": "number",
  "edge_count": "number",
  "path_count": "number",
  "created_at": "ISO 8601 datetime string"
}
```

#### 응답 예시

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "run_id": "667d1815-7718-40fc-bd95-c98101a11ac5",
  "timestamp": "2026-01-27T17:36:35.344603+00:00",
  "total_score": 55.9,
  "learnability_score": 66.2,
  "efficiency_score": 48.5,
  "control_score": 52.9,
  "node_count": 19,
  "edge_count": 239,
  "path_count": 0,
  "created_at": "2026-01-27T17:36:35.344603+00:00",
  "node_evaluations": [...],
  "edge_evaluations": [...],
  "workflow_evaluations": []
}
```

#### HTTP 상태 코드

- `200 OK`: 평가 결과 조회 성공
- `404 Not Found`: run_id에 해당하는 평가 결과를 찾을 수 없음
- `500 Internal Server Error`: 서버 오류

#### 중요 사항

- 평가가 아직 완료되지 않은 경우 `404 Not Found`를 반환합니다.
- `include_details=false`로 설정하면 요약 정보만 반환되어 응답 크기가 줄어듭니다.
- 평가 결과는 분석이 완료된 후에만 조회할 수 있습니다.

### 10. `POST /api/evaluation/full-analysis`

전체 분석을 실행하고 결과를 DB에 저장합니다. 이 엔드포인트는 정적 분석(Node), 전이 분석(Edge), 워크플로우 분석(DFS Paths)을 모두 수행합니다.

#### 요청 본문

```json
{
  "url": "string (required)",
  "user_id": "string (required)"
}
```

#### 응답 형식

```json
{
  "run_id": "string (UUID)",
  "message": "전체 분석이 완료되었습니다."
}
```

#### 응답 예시

```json
{
  "run_id": "667d1815-7718-40fc-bd95-c98101a11ac5",
  "message": "전체 분석이 완료되었습니다."
}
```

#### HTTP 상태 코드

- `200 OK`: 전체 분석이 성공적으로 완료됨
- `400 Bad Request`: 요청 데이터가 유효하지 않음 (URL이 없거나 형식이 잘못됨)
- `500 Internal Server Error`: 분석 실행 중 오류 발생

#### 중요 사항

- 이 엔드포인트는 **동기적으로 실행**되며, 분석이 완료될 때까지 응답을 기다립니다.
- 분석에는 시간이 오래 걸릴 수 있으므로 타임아웃 설정을 충분히 해야 합니다.
- 분석 결과는 자동으로 Supabase DB에 저장되며, JSON 파일도 프로젝트 루트에 생성됩니다.
- 분석이 완료되면 `/api/evaluation/{run_id}` 엔드포인트로 결과를 조회할 수 있습니다.
- 분석 실패 시 run 상태가 `failed`로 업데이트됩니다.
- `user_id`는 run의 `metadata`에 저장됩니다.

#### 분석 결과 저장 구조

분석 결과는 다음 테이블에 저장됩니다:

- **site_evaluations**: 전체 평가 요약 정보 (총점, 카테고리별 점수, 요약 통계)
- **node_evaluations**: 노드별 정적 분석 결과 (learnability, control 점수 및 상세 항목)
- **edge_evaluations**: 엣지별 전환 분석 결과 (efficiency, control 점수, 지연 시간 정보)
- **workflow_evaluations**: 워크플로우 분석 결과

## CORS 설정

프론트엔드가 백엔드 API를 호출할 수 있도록 CORS가 활성화되어 있어야 합니다.

예시 (FastAPI):
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 실시간 업데이트

프론트엔드는 3초마다 자동으로 `/api/runs/{run_id}/monitor` 엔드포인트를 호출합니다.
따라서 해당 엔드포인트는 빠르게 응답해야 하며, 캐싱이나 최적화를 고려하는 것이 좋습니다.

## 에러 처리

모든 API는 표준 HTTP 상태 코드를 반환해야 합니다:
- `200 OK`: 성공
- `404 Not Found`: Run ID를 찾을 수 없음
- `500 Internal Server Error`: 서버 오류

에러 응답 형식:
```json
{
  "detail": "에러 메시지"
}
```
