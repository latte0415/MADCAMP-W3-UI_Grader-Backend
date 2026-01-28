"""
Dramatiq 워커 실행 엔트리포인트

실행 방법:
1. python -m workers.worker
2. dramatiq workers.broker workers.tasks

환경변수:
- REDIS_URL: Redis 연결 URL (기본값: redis://localhost:6379/0)
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 로깅 시스템 초기화 (워커 시작 시 명시적으로 초기화)
from utils.logger import setup_logging, get_logger
setup_logging("INFO")

logger = get_logger(__name__)
logger.info("=" * 60)
logger.info("워커 프로세스 시작")
logger.info("=" * 60)

# tasks 모듈을 import하여 actor들이 등록되도록 함
from workers import tasks  # noqa: F401
from workers import broker  # noqa: F401

logger.info("워커 모듈 로드 완료")
try:
    declared_actors = broker.broker.get_declared_actors()
    if isinstance(declared_actors, dict):
        actor_names = list(declared_actors.keys())
    else:
        actor_names = list(declared_actors) if declared_actors else []
    logger.info(f"등록된 액터: {actor_names}")
except Exception as e:
    logger.debug(f"액터 목록 조회 실패 (계속 진행): {e}")

import dramatiq.cli

if __name__ == "__main__":
    logger.info("Dramatiq CLI 시작")
    # Dramatiq CLI에 필요한 인자 설정
    # dramatiq broker module 형식으로 실행
    sys.argv = ["dramatiq", "workers.broker", "workers.tasks"]
    
    # dramatiq CLI 실행
    try:
        dramatiq.cli.main()
    except KeyboardInterrupt:
        logger.info("워커 프로세스 종료 (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"워커 프로세스 에러: {e}", exc_info=True)
        raise
