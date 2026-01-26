# 구현 현황

## 구현 완료 항목

### 노드 생성
- 상태: 구현 완료
- 위치: `services/node_service.py`의 `create_or_get_node()`
- 형태: 페이지 상태 수집 → 해시/지문 생성 → 기존 노드 조회 → 없으면 삽입 및 아티팩트 업로드

### 액션 추출
- 상태: 구현 완료
- 위치: `utils/action_extractor.py`의 `extract_actions_from_page()`
- 형태: 페이지의 인터랙션 가능한 요소를 스캔하여 액션 리스트 생성

### 액션 후, 엣지 생성
- 상태: 구현 완료
- 위치: `services/edge_service.py`의 `perform_and_record_edge()` / `record_edge()`
- 형태: 액션 수행 → to_node 생성/조회 → depth 분류 → 엣지 기록

### 노드 조회 후, 없으면 생성
- 상태: 구현 완료
- 위치: `services/node_service.py`의 `create_or_get_node()`
- 형태: `run_id + url_normalized + a11y_hash + state_hash` 기준으로 조회 후 없으면 생성

### 노드 파일까지 같이 싹 조회
- 상태: 구현 완료
- 위치: `services/node_service.py`의 `get_node_with_artifacts()`
- 형태: 노드 조회 후 `dom/css/a11y/screenshot/storage` 아티팩트까지 다운로드하여 반환

### 입력 필드 기반 액션 필터 유틸
- 상태: 구현 완료
- 위치: `utils/action_extractor.py`의 `filter_input_required_actions()`
- 형태: 액션 리스트에서 텍스트 입력/드롭다운/토글에 해당하는 액션만 필터링

### 입력 액션을 pending_actions에 저장
- 상태: 구현 완료
- 위치: `services/pending_action_service.py`의 `create_pending_action()`
- 형태: `run_id/from_node_id + action_*` 최소 요건으로 pending_actions 테이블에 insert

### pending_actions 조회
- 상태: 구현 완료
- 위치: `services/pending_action_service.py`의 `list_pending_actions()`
- 형태: `run_id` 기준으로 조회, 필요 시 `from_node_id/status`로 필터링