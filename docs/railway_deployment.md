# Railway 배포 가이드

이 문서는 Railway를 사용하여 백엔드를 배포하는 방법을 설명합니다.

## 사전 준비사항

1. **Railway 계정 생성**: [railway.app](https://railway.app)에서 계정 생성
2. **GitHub 저장소**: 코드가 GitHub에 푸시되어 있어야 함
3. **환경 변수 준비**: 아래 환경 변수 목록 확인

## 배포 단계별 체크리스트

배포 전 확인사항:
- [ ] GitHub 저장소에 코드가 푸시되어 있음
- [ ] Supabase 프로젝트 URL과 Service Key 준비됨
- [ ] OpenAI API 키 준비됨
- [ ] Railway 계정 생성 완료

## 배포 단계

### 1. Railway 프로젝트 생성

1. Railway 대시보드에서 "New Project" 클릭
2. "Deploy from GitHub repo" 선택
3. GitHub 저장소 선택 및 연결

### 2. Redis 서비스 추가

워커가 Redis를 사용하므로 Redis 서비스를 먼저 추가해야 합니다.

1. 프로젝트에서 "New" → "Database" → "Add Redis" 선택
2. Redis 인스턴스가 생성되면 자동으로 `REDIS_URL` 환경 변수가 설정됩니다
3. **중요**: Redis 서비스의 "Variables" 탭에서 `REDIS_URL` 값을 복사해두세요 (다른 서비스에서 사용)

### 3. API 서비스 배포

1. 프로젝트에서 "New" → "GitHub Repo" 선택 (또는 이미 연결된 경우)
2. 저장소 선택
3. 서비스 이름: `api` (또는 원하는 이름)
4. Root Directory: `/` (기본값)
5. Build Command: (Dockerfile 사용 시 자동)
6. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

**환경 변수 설정:**
API 서비스의 "Variables" 탭에서 다음 변수들을 설정합니다:

- `SUPABASE_URL`: Supabase 프로젝트 URL (예: `https://xxxxx.supabase.co`)
- `SUPABASE_SERVICE_KEY`: Supabase service role key
- `OPENAI_API_KEY`: OpenAI API 키
- `REDIS_URL`: Redis 서비스의 연결 URL (Redis 서비스의 Variables에서 복사)
- `LANGCHAIN_TRACING`: `false` (또는 `true`로 설정)
- `LANGCHAIN_API_KEY`: LangSmith API 키 (트레이싱 사용 시만)
- `WORKER_AUTO_START`: `false` (워커는 별도 서비스로 실행하므로 false)
- `ENVIRONMENT`: `production` (선택사항, CORS 설정을 위해 설정 권장)

**참고**: 
- Railway는 `PORT` 환경 변수를 자동으로 제공하므로 설정할 필요가 없습니다.
- Railway는 `RAILWAY_ENVIRONMENT` 환경 변수를 자동으로 설정하므로, CORS는 자동으로 배포 환경으로 인식됩니다.

### 4. 워커 서비스 배포

워커를 별도 서비스로 실행해야 합니다.

1. 프로젝트에서 "New" → "GitHub Repo" 선택
2. **같은 저장소** 선택 (API 서비스와 동일한 저장소)
3. 서비스 이름: `worker` (또는 원하는 이름)
4. Root Directory: `/` (기본값)
5. Build Command: (Dockerfile 사용 시 자동으로 빌드됨)
6. **Start Command**: `python -m workers.worker` (반드시 설정!)

**중요 사항:**
- 워커 서비스는 API 서비스와 **같은 저장소**를 사용하지만 **별도의 서비스**입니다
- 워커 서비스는 포트를 노출할 필요가 없으므로 "Generate Domain"을 하지 않아도 됩니다
- 워커 서비스는 백그라운드에서 계속 실행되어야 하므로 항상 실행 상태를 유지합니다
- **Start Command를 반드시 설정해야 합니다**: Railway 대시보드 → Worker 서비스 → Settings → Deploy → Start Command에 `python -m workers.worker` 입력
- Start Command를 설정하지 않으면 Dockerfile의 기본 CMD(`uvicorn`)가 실행되어 오류가 발생합니다

**환경 변수 설정:**
워커 서비스의 "Variables" 탭에서 다음 변수들을 설정합니다:

- `SUPABASE_URL`: API 서비스와 동일한 값
- `SUPABASE_SERVICE_KEY`: API 서비스와 동일한 값
- `OPENAI_API_KEY`: API 서비스와 동일한 값
- `REDIS_URL`: API 서비스와 동일한 Redis URL (같은 Redis 인스턴스 사용)
- `LANGCHAIN_TRACING`: API 서비스와 동일한 값 (선택적)
- `LANGCHAIN_API_KEY`: API 서비스와 동일한 값 (선택적)
- `WORKER_AUTO_START`: 설정하지 않음 (워커 서비스이므로 불필요)

**팁**: 환경 변수를 프로젝트 레벨에서 설정하면 모든 서비스에서 공유할 수 있습니다:
1. 프로젝트 설정 → "Variables" 탭
2. 공유할 환경 변수 추가
3. 각 서비스에서 "Use Project Variable" 선택

**중요:** 워커 서비스는 같은 Redis 인스턴스를 공유해야 합니다.

### 5. 환경 변수 공유 설정 (선택사항)

여러 서비스에서 동일한 환경 변수를 사용하는 경우, 프로젝트 레벨 변수를 사용하면 편리합니다:

1. 프로젝트 설정 → "Variables" 탭 클릭
2. 공유할 환경 변수 추가 (예: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY`)
3. 각 서비스(API, Worker)의 "Variables" 탭에서 해당 변수 옆의 "Use Project Variable" 체크박스 선택

**주의**: `REDIS_URL`은 Redis 서비스에서 자동 생성되므로, 다른 서비스에서는 수동으로 설정해야 합니다.

### 6. 배포 완료 확인

모든 서비스가 정상적으로 배포되었는지 확인:

1. **API 서비스**:
   - [ ] 빌드가 성공적으로 완료됨
   - [ ] 서비스가 "Running" 상태임
   - [ ] 공개 URL에서 `{"status": "ok"}` 응답 확인

2. **워커 서비스**:
   - [ ] 빌드가 성공적으로 완료됨
   - [ ] 서비스가 "Running" 상태임
   - [ ] 로그에 "워커 프로세스 시작" 메시지 확인
   - [ ] 로그에 "등록된 액터" 목록 확인

3. **Redis 서비스**:
   - [ ] 서비스가 "Running" 상태임
   - [ ] `REDIS_URL` 환경 변수가 설정되어 있음

## 환경 변수 목록

### 필수 환경 변수

| 변수명 | 설명 | 예시 |
|--------|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL | `https://xxxxx.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Supabase service role key | `eyJhbGc...` |
| `OPENAI_API_KEY` | OpenAI API 키 | `sk-...` |
| `REDIS_URL` | Redis 연결 URL | `redis://default:password@redis.railway.internal:6379` |

### 선택적 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `LANGCHAIN_TRACING` | LangSmith 트레이싱 사용 여부 | `false` |
| `LANGCHAIN_API_KEY` | LangSmith API 키 | - |
| `WORKER_AUTO_START` | 워커 자동 시작 (API 서비스에서만) | `false` |
| `PORT` | 서버 포트 (Railway가 자동 설정) | `8000` |

## 배포 확인

### API 서비스 확인

1. Railway 대시보드에서 API 서비스 선택
2. "Settings" → "Generate Domain" 클릭하여 공개 URL 생성
3. 브라우저에서 `https://your-domain.railway.app/` 접속
4. `{"status": "ok"}` 응답 확인

### 워커 서비스 확인

1. Railway 대시보드에서 워커 서비스 선택
2. "Logs" 탭에서 워커 로그 확인
3. 다음과 같은 로그가 보여야 합니다:
   ```
   워커 프로세스 시작
   등록된 액터: [...]
   ```

### Redis 연결 확인

1. API 서비스와 워커 서비스 모두에서 `REDIS_URL` 환경 변수 확인
2. 같은 Redis 인스턴스를 가리키는지 확인

## 트러블슈팅

### 문제: Playwright 브라우저 설치 실패

**해결책:**
- Dockerfile에 브라우저 의존성이 포함되어 있습니다
- 빌드 로그에서 오류 확인
- 필요시 Dockerfile의 의존성 목록 업데이트

### 문제: 워커가 작업을 처리하지 않음

**확인사항:**
1. 워커 서비스가 실행 중인지 확인 (Railway 대시보드에서 "Running" 상태 확인)
2. `REDIS_URL`이 올바르게 설정되었는지 확인
   - API 서비스와 워커 서비스 모두에서 동일한 `REDIS_URL` 사용 확인
   - Redis 서비스의 Variables에서 URL 복사하여 사용
3. API 서비스와 워커 서비스가 같은 Redis를 사용하는지 확인
   - 두 서비스의 `REDIS_URL`이 정확히 동일한지 확인
4. 워커 로그에서 오류 확인
   - "워커 프로세스 시작" 메시지 확인
   - "등록된 액터" 목록이 비어있지 않은지 확인
   - Redis 연결 오류 메시지 확인
5. Redis 연결 테스트:
   - API 서비스에서 작업을 생성하고 워커 로그에서 처리 여부 확인

### 문제: 환경 변수 누락 오류

**해결책:**
1. 각 서비스의 "Variables" 탭에서 필수 환경 변수 확인
2. 프로젝트 레벨 변수 사용 시 서비스에서 "Use Project Variable" 선택 확인

### 문제: 포트 바인딩 오류

**해결책:**
- Railway는 `PORT` 환경 변수를 자동으로 제공합니다
- Start Command에서 `$PORT` 사용 확인
- Dockerfile의 EXPOSE 포트는 Railway가 자동으로 처리합니다

### 문제: 빌드 실패

**확인사항:**
1. Dockerfile이 프로젝트 루트에 있는지 확인
2. requirements.txt의 모든 패키지가 설치 가능한지 확인
3. 빌드 로그에서 구체적인 오류 메시지 확인
4. Playwright 브라우저 설치 오류인 경우:
   - Dockerfile에 필요한 시스템 패키지가 모두 포함되어 있는지 확인
   - 빌드 로그에서 "playwright install" 단계 확인
5. 메모리 부족 오류인 경우:
   - Railway 서비스의 리소스 할당량 확인
   - 필요시 더 큰 인스턴스로 업그레이드

### 문제: Worker 서비스에서 "uvicorn could not be found" 오류

**원인:**
- Worker 서비스의 Start Command가 설정되지 않아 Dockerfile의 기본 CMD(`uvicorn`)가 실행됨
- Worker 서비스는 `python -m workers.worker`를 실행해야 함

**해결책:**
1. Railway 대시보드에서 Worker 서비스 선택
2. "Settings" → "Deploy" 섹션으로 이동
3. "Start Command" 필드에 `python -m workers.worker` 입력
4. "Deploy" 버튼 클릭하여 재배포

**확인:**
- Worker 서비스의 로그에서 "워커 프로세스 시작" 메시지 확인
- "등록된 액터" 목록이 표시되는지 확인

### 문제: API 서비스에서 "on_event is deprecated" 경고

**해결책:**
- 이미 수정되었습니다. `main.py`에서 `lifespan` 이벤트 핸들러를 사용합니다.
- 최신 코드를 배포하면 경고가 사라집니다.

### 문제: 워커 서비스가 계속 재시작됨

**확인사항:**
1. 워커 로그에서 오류 메시지 확인
2. 환경 변수 누락 확인 (특히 `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`)
3. Redis 연결 실패 확인
4. Python 모듈 import 오류 확인

## 모니터링

### 로그 확인

1. Railway 대시보드에서 각 서비스 선택
2. "Logs" 탭에서 실시간 로그 확인
3. 오류 발생 시 로그에서 스택 트레이스 확인

### 메트릭 확인

1. Railway 대시보드에서 각 서비스 선택
2. "Metrics" 탭에서 CPU, 메모리 사용량 확인
3. 비정상적인 리소스 사용 시 서비스 스케일링 고려

## 비용 최적화

1. **서비스 스케일링**: 필요에 따라 CPU/메모리 할당량 조정
2. **Redis 메모리**: 사용량에 따라 Redis 인스턴스 크기 조정
3. **워커 인스턴스**: 트래픽에 따라 워커 서비스 수 조정

## 추가 리소스

- [Railway 공식 문서](https://docs.railway.app)
- [Railway Discord 커뮤니티](https://discord.gg/railway)
