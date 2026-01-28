"""FastAPI 앱 엔트리포인트. health check 엔드포인트 제공."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import monitor, evaluation, runs, nodes
from middleware.exception_handler import register_exception_handlers
from utils.logger import setup_logging, get_logger
from utils.worker_manager import start_worker_background

logger = get_logger(__name__)

# 로깅 시스템 초기화
setup_logging("INFO")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    앱 라이프사이클 관리
    - 시작 시: 워커 자동 시작 및 주기적 완료 체크 워커 시작
    - 종료 시: 정리 작업 (필요 시)
    """
    # 시작 시 실행
    # 워커 자동 시작 (환경변수 WORKER_AUTO_START=true일 때만)
    start_worker_background()
    
    # 주기적 완료 체크 워커 시작 (앱 시작 시 한 번만)
    # Redis 연결이 가능한 경우에만 실행 (워커 서비스에서는 실행되지 않음)
    try:
        from workers.tasks import periodic_completion_check_worker
        from services.graph_completion_service import CHECK_INTERVAL_SECONDS
        
        # Redis 연결 확인 (연결 불가능하면 스킵)
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        test_redis = redis.from_url(redis_url, socket_connect_timeout=2)
        test_redis.ping()
        test_redis.close()
        
        # 첫 번째 체크는 10초 후에 시작 (앱 초기화 시간 확보)
        periodic_completion_check_worker.send_with_options(
            args=(),
            delay=10000  # 10초 후 시작
        )
        logger.info(f"주기적 완료 체크 워커 시작됨 (첫 체크: 10초 후, 이후 {CHECK_INTERVAL_SECONDS}초마다)")
    except Exception as e:
        # Redis 연결 실패 시 로그만 남기고 계속 진행 (워커 서비스에서는 정상)
        logger.debug(f"주기적 완료 체크 워커 시작 스킵 (Redis 연결 불가 또는 워커 서비스): {e}")
    
    yield
    
    # 종료 시 실행 (필요 시)
    # 현재는 특별한 정리 작업이 없음


app = FastAPI(lifespan=lifespan)

# CORS 설정
# 환경에 따라 허용할 origin 목록 결정
def get_allowed_origins():
    """
    환경에 따라 허용할 CORS origin 목록을 반환합니다.
    
    - 모니터링 서버는 항상 허용
    - 로컬 환경: localhost:3000과 웹 서버 허용
    - 배포 환경: 웹 서버만 허용
    """
    # 항상 허용할 origin (모니터링 서버)
    allowed_origins = [
        "https://madcamp-w3-ui-grader-monitoring.vercel.app",
    ]
    
    # 웹 서버 origin
    web_origin = "https://madcamp-w3-ui-grader-web.vercel.app"
    
    # 환경 확인: Railway 환경인지 또는 ENVIRONMENT 환경 변수 확인
    is_production = (
        os.getenv("RAILWAY_ENVIRONMENT") is not None
        or os.getenv("ENVIRONMENT", "").lower() == "production"
        or os.getenv("ENV", "").lower() == "production"
    )
    
    if is_production:
        # 배포 환경: 웹 서버만 허용
        allowed_origins.append(web_origin)
        logger.info("CORS 설정: 배포 환경 - 웹 서버와 모니터링 서버만 허용")
    else:
        # 로컬 환경: localhost:3000과 웹 서버 허용
        allowed_origins.extend([
            "http://localhost:3000",
            web_origin,
        ])
        logger.info("CORS 설정: 로컬 환경 - localhost:3000, 웹 서버, 모니터링 서버 허용")
    
    return allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# 예외 핸들러 등록
register_exception_handlers(app)

# 라우터 등록
app.include_router(monitor.router)
app.include_router(evaluation.router)
app.include_router(runs.router)
app.include_router(nodes.router)


@app.get("/")
def health_check():
    """헬스 체크. Returns: {"status": "ok"}"""
    return {"status": "ok"}