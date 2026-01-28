# 그래프 구축 종료 조건 해결책

## 문제점

기존 시스템에는 다음과 같은 문제가 있었습니다:

1. **그래프 구축이 끝나지 않음**: `start_graph_building`이 첫 워커만 생성하고 종료되며, 그래프 구축이 언제 완료되는지 알 수 없었습니다.
2. **종료 조건 부재**: 최대 엣지 수 제한이나 완료 조건이 없어 그래프가 무한정 확장될 수 있었습니다.
3. **Full analysis 자동 실행 부재**: 그래프 구축이 완료되어도 자동으로 full_analysis가 실행되지 않았습니다.

## 해결책

### 1. 그래프 완료 체크 서비스 추가

`services/graph_completion_service.py` 파일을 생성하여 다음 기능을 구현했습니다:

- **완료 조건 체크**: 최대 엣지 수 제한 (기본값: 500개)
- **완료 처리**: 그래프 구축 완료 시 run 상태를 `completed`로 변경
- **Full analysis 자동 시작**: 완료 시 `run_full_analysis_worker` 워커 호출

### 2. 엣지 카운트 조회 함수 추가

`repositories/edge_repository.py`에 `count_edges_by_run_id` 함수를 추가하여 특정 run의 엣지 개수를 효율적으로 조회할 수 있도록 했습니다.

### 3. 그래프 완료 체크 워커 추가

`workers/tasks.py`에 다음 워커들을 추가했습니다:

- **`check_graph_completion_worker`**: 그래프 구축 완료 여부를 체크하는 워커
- **`run_full_analysis_worker`**: Full analysis를 실행하는 워커

### 4. 액션 워커에서 완료 체크 호출

`process_action_worker`에서 엣지 생성 후 자동으로 그래프 완료 체크 워커를 호출하도록 수정했습니다. 5초 지연 후 실행하여 다른 워커들이 먼저 처리할 수 있도록 했습니다.

## 구현 세부사항

### 완료 조건

현재 구현된 완료 조건:

1. **최대 엣지 수 도달**: 엣지 개수가 `MAX_EDGE_COUNT` (500개)에 도달하면 완료로 간주
2. **Run 상태 확인**: run 상태가 `running`이 아닌 경우 체크 스킵

### 향후 개선 가능한 완료 조건

다음과 같은 추가 완료 조건을 구현할 수 있습니다:

- **일정 시간 동안 새 엣지 부재**: 일정 시간(예: 5분) 동안 새 엣지가 생성되지 않으면 완료로 간주
- **액션 부재**: 더 이상 처리할 액션이 없을 때 완료로 간주
- **최대 노드 수 도달**: 노드 개수 제한 추가

### 설정 값

`services/graph_completion_service.py`에서 다음 설정을 변경할 수 있습니다:

```python
MAX_EDGE_COUNT = 500  # 최대 엣지 수 제한
CHECK_INTERVAL_SECONDS = 30  # 완료 체크 간격 (현재 미사용)
NO_NEW_EDGES_THRESHOLD_SECONDS = 300  # 새 엣지 부재 임계값 (현재 미사용)
```

## 실행 흐름

1. **그래프 구축 시작**: `start_graph_building`이 첫 노드와 워커를 생성
2. **워커 실행**: `process_node_worker`와 `process_action_worker`가 그래프를 구축
3. **엣지 생성**: 각 액션 실행 후 엣지가 생성됨
4. **완료 체크**: 엣지 생성 후 5초 지연 후 `check_graph_completion_worker` 호출
5. **완료 처리**: 최대 엣지 수에 도달하면 `complete_graph_building` 호출
6. **상태 변경**: run 상태를 `completed`로 변경
7. **Full analysis 시작**: `run_full_analysis_worker` 워커 호출
8. **분석 완료**: Full analysis 결과를 DB에 저장

## 주의사항

1. **중복 체크 방지**: 완료 체크 워커가 여러 번 실행될 수 있으므로, `complete_graph_building`에서 run 상태를 확인하여 중복 실행을 방지합니다.

2. **에러 처리**: Full analysis 실행 중 오류가 발생하면 run 상태를 `failed`로 변경합니다.

3. **성능 고려**: 완료 체크는 5초 지연 후 실행되므로, 여러 워커가 동시에 완료 체크를 호출해도 문제없습니다.

## 테스트 방법

1. 분석 시작: `POST /api/evaluation/analyze` 엔드포인트 호출
2. 모니터링: `GET /api/runs/{run_id}/monitor` 엔드포인트로 진행 상황 확인
3. 완료 확인: 엣지 개수가 500개에 도달하면 자동으로 완료 처리됨
4. 결과 확인: `GET /api/evaluation/{run_id}` 엔드포인트로 평가 결과 확인

## 향후 개선 사항

1. **동적 완료 조건**: 사용자가 완료 조건을 설정할 수 있도록 API 파라미터 추가
2. **진행률 표시**: 현재 엣지 개수와 최대 엣지 개수를 모니터링 API에 포함
3. **완료 알림**: 완료 시 웹훅이나 알림 전송 기능 추가
4. **부분 완료**: 일부 노드만 완료된 경우에도 분석 가능하도록 개선
