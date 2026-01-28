"""FastAPI 앱 엔트리포인트. health check 엔드포인트 제공."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import monitor, evaluation, runs
from middleware.exception_handler import register_exception_handlers
from utils.logger import setup_logging

# 로깅 시스템 초기화
setup_logging("INFO")

app = FastAPI()

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