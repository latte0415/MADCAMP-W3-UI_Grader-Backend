# 그래프 정책 정리

## 범위
- 노드/엣지 정의
- 동치 판단 기준
- 주요 컬럼 의미
- 해시/요약 생성 규칙

## 노드 정의
- 노드는 특정 `run_id` 내에서의 **화면 상태**를 의미한다.
- 같은 URL이라도 인증/스토리지/접근성 상태가 다르면 **다른 노드**로 간주한다.

## 노드 동치 판단 기준
- 동치 키: `run_id + url_normalized + a11y_hash + state_hash`
- 위 값이 모두 동일하면 동일 노드로 취급한다.

## 노드 주요 컬럼
- `url`, `url_normalized`: 원본 URL과 정규화 URL
- `a11y_hash`: 접근성 정보 요약의 해시
- `state_hash`: 인증 상태 + 스토리지 지문의 해시
- `content_dom_hash`: 콘텐츠 중심 DOM 해시(선택, 의미적 변화 감지용)
- `auth_state`: 인증 상태 요약(민감 정보 원문 저장 금지)
- `storage_fingerprint`: 스토리지 키/값 해시 지문
- `*_ref`: 아티팩트 파일 경로 참조 (DB에는 경로만 저장)

## 접근성 정보(a11y_info)
- 스냅샷 방식은 레거시로 **주석 처리**되어 사용하지 않는다.
- 현재는 DOM 기반 요약인 `a11y_info`만 사용한다.
- 포맷: `role|label|name|tag|type|aria`
  - `role`: role 속성
  - `label`: aria-label
  - `name`: 텍스트(최대 50자) 또는 aria-labelledby 텍스트
  - `tag`: 태그명 (소문자)
  - `type`: input type
  - `aria`: 주요 상태 속성 요약 (`aria-*` key=value 목록)

## 의미적 정보(콘텐츠 요약)
- 목적: 페이지의 **의미적 변화**(제목/본문/주요 섹션 변화) 감지
- 수집 방식: `content_elements`에서 주요 텍스트를 선택적으로 추출
  - 대상: `h1~h6`, `p`, `span`, `main`, `article`, `div[class*='content']`
  - 조건: 텍스트 길이 5자 이상, 각 타입 최대 10개
  - 포맷: `selector:text[:100]`
- `content_dom_hash`는 위 목록을 정렬 후 해시한 값
- 개인정보/민감정보가 포함될 수 있는 경우 필터링 필요

## 해시 생성 규칙
- `state_hash` = `auth_state` + `storage_fingerprint`를 정렬된 JSON으로 합친 뒤 SHA-256
- `a11y_hash` = `a11y_info` 리스트 정렬 후 합쳐 SHA-256

## 엣지 정의
- 엣지는 노드 간 **액션 전이**를 의미한다.
- `from_node_id` -> `to_node_id` (실패 시 `to_node_id`는 NULL 허용)

## 엣지 주요 컬럼
- `action_type`, `action_target`, `action_value`: 액션 종류/대상/입력값
- `latency_ms`, `outcome`, `error_msg`: 실행 결과 메타
- `depth_diff_type`: 변화 유형 분류(동일/인터랙션/새 페이지/모달 등)

## 뎁스 매핑 규칙
- `new_page` → `route_depth + 1`
- `modal_overlay` → `modal_depth + 1`
- `drawer` → `modal_depth + 1`
- `interaction_only` → `interaction_depth + 1`
- `same_node` → 변화 없음

## 중복/유니크 정책
- 노드: `run_id, url_normalized, a11y_hash, state_hash` 유니크
- 엣지: `run_id, from_node_id, to_node_id, action_type, action_target, action_value` 유니크