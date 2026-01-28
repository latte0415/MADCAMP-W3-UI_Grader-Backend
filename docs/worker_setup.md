# 워커 실행 방법

## 현재 상황

현재 시스템은 **Dramatiq 워커를 별도 프로세스로 실행**해야 합니다.

- **API 서버**: `uvicorn main:app` (FastAPI)
- **워커**: `python -m workers.worker` (Dramatiq)

워커가 실행되지 않으면 작업이 큐에만 쌓이고 처리되지 않습니다.

## 실행 방법

### 방법 1: 수동 실행 (기본)

**터미널 1 - API 서버:**
```bash
uvicorn main:app --reload
```

**터미널 2 - 워커:**
```bash
python -m workers.worker
```

### 방법 2: 자동 실행 (환경변수 설정)

환경변수 `WORKER_AUTO_START=true`를 설정하면 API 서버 시작 시 워커가 자동으로 백그라운드에서 시작됩니다.

**.env 파일에 추가:**
```bash
WORKER_AUTO_START=true
```

**API 서버만 실행:**
```bash
uvicorn main:app --reload
```

워커가 자동으로 백그라운드에서 시작됩니다.

## 주의사항

1. **Redis 필요**: 워커 실행 전에 Redis가 실행 중이어야 합니다.
   ```bash
   docker run -d -p 6379:6379 --name redis redis:latest
   ```

2. **프로덕션 환경**: 프로덕션에서는 워커를 별도 프로세스로 관리하는 것을 권장합니다.
   - systemd 서비스
   - Docker Compose
   - Kubernetes Deployment

3. **자동 시작 제한**: 자동 시작은 개발 환경에서 편의를 위한 기능입니다.
   - 프로덕션에서는 수동 실행 또는 프로세스 관리자를 사용하세요.

## 프로덕션 배포 예시

### Docker Compose

```yaml
version: '3.8'
services:
  api:
    build: .
    command: uvicorn main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    environment:
      - WORKER_AUTO_START=false  # 프로덕션에서는 false
  
  worker:
    build: .
    command: python -m workers.worker
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
  
  redis:
    image: redis:latest
    ports:
      - "6379:6379"
```

### systemd 서비스

**`/etc/systemd/system/worker.service`:**
```ini
[Unit]
Description=Graph Builder Worker
After=network.target redis.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/backend
ExecStart=/usr/bin/python3 -m workers.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**서비스 시작:**
```bash
sudo systemctl enable worker
sudo systemctl start worker
```

## 워커 상태 확인

워커가 실행 중인지 확인하려면:

```python
from utils.worker_manager import is_worker_running

if is_worker_running():
    print("워커가 실행 중입니다.")
else:
    print("워커가 실행되지 않았습니다.")
```

또는 Redis 큐를 확인:

```bash
redis-cli
> LLEN default  # 큐에 대기 중인 작업 수 확인
```
