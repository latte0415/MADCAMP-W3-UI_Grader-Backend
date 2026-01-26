"""
입력 포맷터 레지스트리

label별 입력 포맷터를 등록하고 관리합니다.
"""

from typing import Dict, Callable, Any

# label별 입력 포맷터 등록
_INPUT_FORMATTERS: Dict[str, Callable] = {}


def register_input_formatter(label: str, formatter: Callable) -> None:
    """
    label별 입력 포맷터를 등록합니다.
    
    Args:
        label: 프롬프트 레이블
        formatter: 입력 포맷팅 함수 (**kwargs를 받아서 포맷팅된 문자열 반환)
    
    Examples:
        def my_formatter(**kwargs) -> str:
            data = kwargs.get("data")
            return f"Formatted: {data}"
        
        register_input_formatter("my-label", my_formatter)
    """
    _INPUT_FORMATTERS[label] = formatter


def get_input_formatter(label: str) -> Callable | None:
    """
    label에 해당하는 입력 포맷터를 반환합니다.
    
    Args:
        label: 프롬프트 레이블
    
    Returns:
        포맷터 함수 또는 None
    """
    return _INPUT_FORMATTERS.get(label)


def has_input_formatter(label: str) -> bool:
    """
    label에 등록된 포맷터가 있는지 확인합니다.
    
    Args:
        label: 프롬프트 레이블
    
    Returns:
        포맷터 존재 여부
    """
    return label in _INPUT_FORMATTERS
