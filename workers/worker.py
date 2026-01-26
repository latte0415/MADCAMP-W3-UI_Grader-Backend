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

# tasks 모듈을 import하여 actor들이 등록되도록 함
from workers import tasks  # noqa: F401
from workers import broker  # noqa: F401
import dramatiq.cli

if __name__ == "__main__":
    # Dramatiq CLI에 필요한 인자 설정
    # dramatiq broker module 형식으로 실행
    sys.argv = ["dramatiq", "workers.broker", "workers.tasks"]
    
    # dramatiq CLI 실행
    dramatiq.cli.main()
