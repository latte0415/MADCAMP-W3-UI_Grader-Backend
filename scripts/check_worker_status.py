"""
워커 실행 상태 확인 스크립트

사용법:
    python scripts/check_worker_status.py
"""
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from workers.broker import broker
from utils.logger import get_logger, setup_logging
import redis

logger = get_logger(__name__)
setup_logging("INFO")


def check_redis_connection():
    """Redis 연결 확인"""
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        logger.info(f"Redis URL: {redis_url}")
        
        # Redis URL 파싱
        if redis_url.startswith("redis://"):
            redis_url = redis_url[8:]  # "redis://" 제거
        
        # 호스트와 포트 추출
        if "/" in redis_url:
            host_port, db = redis_url.split("/", 1)
        else:
            host_port, db = redis_url, "0"
        
        if ":" in host_port:
            host, port = host_port.split(":")
            port = int(port)
        else:
            host, port = host_port, 6379
        
        db = int(db)
        
        # Redis 연결 테스트
        r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        r.ping()
        logger.info(f"✅ Redis 연결 성공: {host}:{port}/{db}")
        return True
    except Exception as e:
        logger.error(f"❌ Redis 연결 실패: {e}")
        return False


def check_queue_status():
    """큐 상태 확인"""
    try:
        # Dramatiq 큐 확인
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        
        if redis_url.startswith("redis://"):
            redis_url = redis_url[8:]
        
        if "/" in redis_url:
            host_port, db = redis_url.split("/", 1)
        else:
            host_port, db = redis_url, "0"
        
        if ":" in host_port:
            host, port = host_port.split(":")
            port = int(port)
        else:
            host, port = host_port, 6379
        
        db = int(db)
        
        r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        
        # Dramatiq 큐 키 확인
        queue_keys = r.keys("dramatiq:*")
        
        logger.info(f"\n{'='*60}")
        logger.info("큐 상태:")
        logger.info(f"{'='*60}")
        
        if queue_keys:
            logger.info(f"발견된 큐 키: {len(queue_keys)}개")
            for key in sorted(queue_keys)[:20]:  # 최대 20개만 표시
                count = r.llen(key) if r.type(key) == "list" else "N/A"
                logger.info(f"  - {key}: {count}")
            if len(queue_keys) > 20:
                logger.info(f"  ... (총 {len(queue_keys)}개, 처음 20개만 표시)")
        else:
            logger.info("큐에 메시지가 없습니다.")
        
        return True
    except Exception as e:
        logger.error(f"큐 상태 확인 실패: {e}", exc_info=True)
        return False


def main():
    print(f"\n{'='*60}")
    print("워커 상태 확인")
    print(f"{'='*60}\n")
    
    # 1. Redis 연결 확인
    logger.info("1. Redis 연결 확인 중...")
    redis_ok = check_redis_connection()
    
    if not redis_ok:
        print("\n❌ Redis 연결 실패. 워커를 실행할 수 없습니다.")
        print("\nRedis 실행 방법:")
        print("  docker run -d -p 6379:6379 --name redis redis:latest")
        print("  또는")
        print("  docker start redis")
        sys.exit(1)
    
    # 2. 큐 상태 확인
    logger.info("\n2. 큐 상태 확인 중...")
    check_queue_status()
    
    # 3. 워커 실행 안내
    print(f"\n{'='*60}")
    print("워커 실행 안내:")
    print(f"{'='*60}")
    print("워커를 실행하려면 다음 명령을 실행하세요:")
    print("  python -m workers.worker")
    print("\n또는")
    print("  dramatiq workers.broker workers.tasks")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
