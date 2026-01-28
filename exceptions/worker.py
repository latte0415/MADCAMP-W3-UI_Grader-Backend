"""Worker 레이어 예외 클래스"""
from typing import Optional, Dict, Any
from exceptions.base import BaseAppException


class WorkerException(BaseAppException):
    """Worker 레이어 기본 예외"""
    pass


class WorkerTaskError(WorkerException):
    """워커 작업 실패 시 발생하는 예외"""
    
    def __init__(
        self,
        task_type: str,
        run_id: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Args:
            task_type: 작업 타입 (예: "process_node", "process_action")
            run_id: 탐색 세션 ID
            reason: 실패 이유
            details: 추가 상세 정보
            original_error: 원본 예외
        """
        message = f"워커 작업 실패: {task_type}"
        if run_id:
            message += f" (run_id: {run_id})"
        if reason:
            message += f" - {reason}"
        
        super().__init__(message, details, original_error)
        self.task_type = task_type
        self.run_id = run_id
        self.reason = reason


class LockAcquisitionError(WorkerException):
    """락 획득 실패 시 발생하는 예외"""
    
    def __init__(
        self,
        lock_type: str,
        resource_id: Optional[str] = None,
        timeout: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            lock_type: 락 타입 (예: "node", "action")
            resource_id: 리소스 ID
            timeout: 타임아웃 시간 (초)
            details: 추가 상세 정보
        """
        message = f"락 획득 실패: {lock_type}"
        if resource_id:
            message += f" (리소스: {resource_id})"
        if timeout:
            message += f" (타임아웃: {timeout}초)"
        
        super().__init__(message, details)
        self.lock_type = lock_type
        self.resource_id = resource_id
        self.timeout = timeout
