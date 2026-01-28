"""FastAPI 앱 엔트리포인트. health check 엔드포인트 제공."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import monitor, evaluation, runs
from middleware.exception_handler import register_exception_handlers
from utils.logger import setup_logging, get_logger
from utils.worker_manager import start_worker_background

logger = get_logger(__name__)

# 로깅 시스템 초기화
setup_logging("INFO")

app = FastAPI()

# 워커 자동 시작 (환경변수 WORKER_AUTO_START=true일 때만)
start_worker_background()

# 주기적 완료 체크 워커 시작 (앱 시작 시 한 번만)
@app.on_event("startup")
def start_periodic_completion_check():
    """앱 시작 시 주기적 완료 체크 워커를 시작합니다."""
    try:
        from workers.tasks import periodic_completion_check_worker
        from services.graph_completion_service import CHECK_INTERVAL_SECONDS
        
        # 첫 번째 체크는 10초 후에 시작 (앱 초기화 시간 확보)
        periodic_completion_check_worker.send_with_options(
            args=(),
            delay=10000  # 10초 후 시작
        )
        logger.info(f"주기적 완료 체크 워커 시작됨 (첫 체크: 10초 후, 이후 {CHECK_INTERVAL_SECONDS}초마다)")
    except Exception as e:
        logger.error(f"주기적 완료 체크 워커 시작 실패: {e}", exc_info=True)

# CORS 설정 (모든 origin 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 origin 허용
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


@app.get("/")
def health_check():
    """헬스 체크. Returns: {"status": "ok"}"""
    return {"status": "ok"}