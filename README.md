# Backend

웹 탐색 그래프(runs/nodes/edges) 수집, AI 연동(LLM·run_memory·filter-action), Dramatiq 워커를 담당하는 백엔드입니다.

## 기술 스택

- **API**: FastAPI
- **브라우저 자동화**: Playwright
- **DB·Storage**: Supabase (PostgreSQL, Storage)
- **AI**: LangChain, OpenAI (gpt-4o / gpt-4o-mini)
- **작업 큐**: Dramatiq, Redis

## 환경 변수

| 변수 | 설명 |
|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key |
| `OPENAI_API_KEY` | OpenAI API 키 |
| `REDIS_URL` | Redis 연결 URL (기본값: `redis://localhost:6379/0`) |
| `LANGCHAIN_TRACING` | LangSmith 트레이싱 사용 여부 (`true` / `false`) |
| `LANGCHAIN_API_KEY` | LangSmith API 키 (트레이싱 사용 시) |

`.env`에 설정하거나 `python-dotenv`로 로드합니다.

## 설치·실행

```bash
pip install -r requirements.txt
```

- **API 서버**: `uvicorn main:app`
- **워커**: `python -m workers.worker` (Redis 실행 필요)

로컬 Redis: `docker run -d -p 6379:6379 --name redis redis:latest`

## 디렉터리 구조

| 경로 | 설명 |
|------|------|
| `main.py` | FastAPI 앱 엔트리포인트 (health check) |
| `services/` | 노드·엣지·AI·pending_action 비즈니스 로직 |
| `repositories/` | nodes, edges, run_memory, pending_actions 데이터 접근 |
| `infra/` | Supabase 클라이언트, LangChain(LLM·에이전트·툴·프롬프트) |
| `utils/` | 액션 추출, 해시 생성, 상태 수집, 그래프 분류, LLM 결과 추출 |
| `schemas/` | 액션 스키마 (Action, ActionType 등) |
| `dependencies/` | Repository·Service 인스턴스 관리 (DI) |
| `workers/` | Dramatiq 브로커·태스크·워커 실행 |
| `scripts/` | DB 스키마·마이그레이션 SQL |
| `docs/` | DB 스키마, 정책, 구현 현황, 스크립트 설명 |
| `tests/` | 노드·엣지·AI 플로우·필터 액션 등 테스트 |

## 상세 문서

- [docs/db.md](docs/db.md) — Supabase DB 스키마 (runs, nodes, edges, run_memory, pending_actions)
- [docs/policy.md](docs/policy.md) — 그래프 정책 (노드/엣지 정의, 동치 기준)
- [docs/todo.md](docs/todo.md) — 구현 현황
- [docs/scripts.md](docs/scripts.md) — SQL 스크립트 실행 순서·용도
