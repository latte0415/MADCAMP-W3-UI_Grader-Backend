"""FastAPI 전역 예외 핸들러"""
from typing import Dict, Any
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from exceptions.base import BaseAppException
from exceptions.repository import (
    RepositoryException,
    EntityNotFoundError,
    DatabaseConnectionError
)
from exceptions.service import ServiceException
from exceptions.worker import WorkerException
from utils.logger import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app):
    """
    FastAPI 앱에 예외 핸들러 등록
    
    Args:
        app: FastAPI 앱 인스턴스
    """
    
    @app.exception_handler(BaseAppException)
    async def base_app_exception_handler(request: Request, exc: BaseAppException):
        """커스텀 예외 핸들러"""
        logger.error(f"커스텀 예외 발생: {exc.message}", exc_info=exc.original_error)
        
        # 예외 타입별 HTTP 상태 코드 결정
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        if isinstance(exc, EntityNotFoundError):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, DatabaseConnectionError):
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif isinstance(exc, RepositoryException):
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        elif isinstance(exc, ServiceException):
            status_code = status.HTTP_400_BAD_REQUEST
        elif isinstance(exc, WorkerException):
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        return JSONResponse(
            status_code=status_code,
            content=exc.to_dict()
        )
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """HTTP 예외 핸들러"""
        logger.warning(f"HTTP 예외 발생: {exc.status_code} - {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTPException",
                "message": exc.detail,
                "status_code": exc.status_code
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """요청 검증 예외 핸들러"""
        logger.warning(f"요청 검증 실패: {exc.errors()}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "ValidationError",
                "message": "요청 데이터 검증 실패",
                "details": exc.errors()
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """예상치 못한 예외 핸들러"""
        logger.error(f"예상치 못한 예외 발생: {type(exc).__name__}", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "서버 내부 오류가 발생했습니다.",
                "type": type(exc).__name__
            }
        )
