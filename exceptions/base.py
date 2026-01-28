"""기본 예외 클래스"""
from typing import Optional, Dict, Any


class BaseAppException(Exception):
    """모든 커스텀 예외의 기본 클래스"""
    
    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None
    ):
        """
        Args:
            message: 에러 메시지
            details: 추가 상세 정보 딕셔너리
            original_error: 원본 예외 (있는 경우)
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.original_error = original_error
    
    def __str__(self) -> str:
        return self.message
    
    def to_dict(self) -> Dict[str, Any]:
        """예외를 딕셔너리로 변환 (API 응답용)"""
        result = {
            "error": self.__class__.__name__,
            "message": self.message
        }
        if self.details:
            result["details"] = self.details
        if self.original_error:
            result["original_error"] = str(self.original_error)
        return result
