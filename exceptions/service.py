"""Service 레이어 예외 클래스"""
from typing import Optional, Dict, Any
from exceptions.base import BaseAppException


class ServiceException(BaseAppException):
    """Service 레이어 기본 예외"""
    pass


class ActionExecutionError(ServiceException):
    """액션 실행 실패 시 발생하는 예외"""
    
    def __init__(
        self,
        action_type: str,
        action_target: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Args:
            action_type: 액션 타입 (click, fill, navigate 등)
            action_target: 액션 대상
            reason: 실패 이유
            details: 추가 상세 정보
            original_error: 원본 예외
        """
        message = f"액션 실행 실패: {action_type}"
        if action_target:
            message += f" / {action_target}"
        if reason:
            message += f" - {reason}"
        
        super().__init__(message, details, original_error)
        self.action_type = action_type
        self.action_target = action_target
        self.reason = reason


class AIServiceError(ServiceException):
    """AI 서비스 호출 실패 시 발생하는 예외"""
    
    def __init__(
        self,
        operation: str,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Args:
            operation: 수행한 작업 (예: "update-run-memory", "filter-action")
            reason: 실패 이유
            details: 추가 상세 정보
            original_error: 원본 예외
        """
        message = f"AI 서비스 호출 실패: {operation}"
        if reason:
            message += f" - {reason}"
        
        super().__init__(message, details, original_error)
        self.operation = operation
        self.reason = reason


class ModerationError(ServiceException):
    """Moderation 검사 실패 시 발생하는 예외"""
    
    def __init__(
        self,
        reason: Optional[str] = None,
        moderation_result: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Args:
            reason: 실패 이유
            moderation_result: Moderation 검사 결과
            details: 추가 상세 정보
            original_error: 원본 예외
        """
        message = "Moderation 검사 실패"
        if reason:
            message += f": {reason}"
        
        super().__init__(message, details, original_error)
        self.moderation_result = moderation_result or {}
