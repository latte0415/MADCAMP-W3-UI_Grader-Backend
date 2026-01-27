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
