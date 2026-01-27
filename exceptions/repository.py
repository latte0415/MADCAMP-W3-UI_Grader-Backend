"""Repository 레이어 예외 클래스"""
from typing import Optional, Dict, Any
from exceptions.base import BaseAppException


class RepositoryException(BaseAppException):
    """Repository 레이어 기본 예외"""
    pass


class EntityNotFoundError(RepositoryException):
    """엔티티를 찾을 수 없을 때 발생하는 예외"""
    
    def __init__(
        self,
        entity_type: str,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Args:
            entity_type: 엔티티 타입 (예: "노드", "엣지", "run")
            entity_id: 엔티티 ID (선택적)
            details: 추가 상세 정보
        """
        if entity_id:
            message = f"{entity_type}을(를) 찾을 수 없습니다: {entity_id}"
        else:
            message = f"{entity_type}을(를) 찾을 수 없습니다."
        
        super().__init__(message, details)
        self.entity_type = entity_type
        self.entity_id = entity_id


class EntityCreationError(RepositoryException):
    """엔티티 생성 실패 시 발생하는 예외"""
    
    def __init__(
        self,
        entity_type: str,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Args:
            entity_type: 엔티티 타입
            reason: 실패 이유
            details: 추가 상세 정보
            original_error: 원본 예외
        """
        message = f"{entity_type} 생성 실패"
        if reason:
            message += f": {reason}"
        else:
            message += ": 데이터가 반환되지 않았습니다."
        
        super().__init__(message, details, original_error)
        self.entity_type = entity_type
        self.reason = reason


class EntityUpdateError(RepositoryException):
    """엔티티 업데이트 실패 시 발생하는 예외"""
    
    def __init__(
        self,
        entity_type: str,
        entity_id: Optional[str] = None,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Args:
            entity_type: 엔티티 타입
            entity_id: 엔티티 ID
            reason: 실패 이유
            details: 추가 상세 정보
            original_error: 원본 예외
        """
        message = f"{entity_type} 업데이트 실패"
        if entity_id:
            message += f" (ID: {entity_id})"
        if reason:
            message += f": {reason}"
        else:
            message += ": 데이터가 반환되지 않았습니다."
        
        super().__init__(message, details, original_error)
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.reason = reason


class DatabaseConnectionError(RepositoryException):
    """데이터베이스 연결 실패 시 발생하는 예외"""
    
    def __init__(
        self,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Args:
            reason: 실패 이유
            details: 추가 상세 정보
            original_error: 원본 예외
        """
        message = "데이터베이스 연결 실패"
        if reason:
            message += f": {reason}"
        
        super().__init__(message, details, original_error)
        self.reason = reason
