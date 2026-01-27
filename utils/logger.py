"""구조화된 로깅 시스템"""
import logging
import sys
from typing import Optional, Dict, Any
from datetime import datetime


class ContextFilter(logging.Filter):
    """컨텍스트 정보를 로그 레코드에 추가하는 필터"""
    
    def __init__(self):
        super().__init__()
        self.context: Dict[str, Any] = {}
    
    def add_context(self, key: str, value: Any):
        """컨텍스트 정보 추가"""
        self.context[key] = value
    
    def clear_context(self):
        """컨텍스트 정보 초기화"""
        self.context.clear()
    
    def filter(self, record: logging.LogRecord) -> bool:
        """로그 레코드에 컨텍스트 정보 추가"""
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


# 전역 컨텍스트 필터 인스턴스
_context_filter = ContextFilter()


def setup_logging(level: str = "INFO") -> None:
    """
    로깅 시스템 초기화
    
    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # 로그 포맷 설정
    log_format = "%(asctime)s [%(levelname)s] [%(name)s]"
    
    # 컨텍스트 정보가 있으면 추가
    context_parts = []
    if hasattr(_context_filter, 'context'):
        if 'run_id' in _context_filter.context:
            context_parts.append("run:%(run_id)s")
        if 'node_id' in _context_filter.context:
            context_parts.append("node:%(node_id)s")
        if 'worker_type' in _context_filter.context:
            context_parts.append("[%(worker_type)s]")
    
    if context_parts:
        log_format += " " + " ".join(context_parts)
    
    log_format += " %(message)s"
    
    # 로거 설정
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 루트 로거에 컨텍스트 필터 추가
    root_logger = logging.getLogger()
    if _context_filter not in root_logger.filters:
        root_logger.addFilter(_context_filter)
    
    # httpx의 HTTP 요청 로그는 WARNING 레벨로 설정 (INFO 레벨에서 숨김)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    로거 인스턴스 가져오기
    
    Args:
        name: 로거 이름 (보통 __name__ 사용)
    
    Returns:
        Logger 인스턴스
    """
    return logging.getLogger(name)


def set_context(run_id: Optional[str] = None, node_id: Optional[str] = None, worker_type: Optional[str] = None):
    """
    로깅 컨텍스트 설정
    
    Args:
        run_id: 탐색 세션 ID
        node_id: 노드 ID
        worker_type: 워커 타입 (NODE, ACTION, PENDING)
    """
    if run_id:
        _context_filter.add_context("run_id", str(run_id)[:8] if len(str(run_id)) > 8 else str(run_id))
    if node_id:
        _context_filter.add_context("node_id", str(node_id)[:8] if len(str(node_id)) > 8 else str(node_id))
    if worker_type:
        _context_filter.add_context("worker_type", worker_type)


def clear_context():
    """로깅 컨텍스트 초기화"""
    _context_filter.clear_context()


# 기본 로깅 설정 (INFO 레벨)
setup_logging("INFO")
