"""
Redis 브로커 설정

순수 Redis를 사용하여 Dramatiq 브로커를 구성합니다.
메모리 기반의 빠른 작업 큐 처리를 위해 Redis를 사용합니다.

환경변수:
- REDIS_URL: Redis 연결 URL (예: redis://localhost:6379/0)
  기본값: redis://localhost:6379/0

로컬 개발 시:
  docker run -d -p 6379:6379 --name redis redis:latest
"""

import os
from dotenv import load_dotenv
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend

# 환경 변수 로드
load_dotenv()

# 환경변수에서 Redis URL 가져오기 (기본값: 로컬 Redis)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Redis URL 로깅 (디버깅용)
from utils.logger import get_logger
logger = get_logger(__name__)

if REDIS_URL == "redis://localhost:6379/0":
    logger.warning("⚠️  REDIS_URL 환경 변수가 설정되지 않았습니다. 기본값(localhost:6379)을 사용합니다.")
    logger.warning("⚠️  Railway 배포 환경에서는 Redis 서비스의 REDIS_URL을 설정해야 합니다.")
else:
    logger.info(f"✓ Redis URL 설정됨: {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else REDIS_URL}")

# Redis 브로커 인스턴스 생성
broker = RedisBroker(url=REDIS_URL)

# Results middleware 추가 (작업 결과 저장)
# Redis를 백엔드로 사용하여 작업 결과를 저장
broker.add_middleware(Results(backend=RedisBackend(url=REDIS_URL)))

# Dramatiq에 브로커 설정
from dramatiq import set_broker
set_broker(broker)
