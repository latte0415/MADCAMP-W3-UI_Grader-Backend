"""
update-run-memory chain용 입력 포맷터
"""

from typing import Dict, Any
from infra.langchain.prompts import get_human_input
from . import register_input_formatter


def format_update_run_memory_input(
    run_memory: Dict[str, Any]
) -> str:
    """
    update-run-memory chain용 입력 포맷팅
    
    Args:
        run_memory: run_memory의 content 딕셔너리
    
    Returns:
        포맷팅된 human input 문자열
    """
    human_template = get_human_input("update-run-memory")
    
    # run_memory를 JSON 문자열로 변환
    import json
    run_memory_str = json.dumps(run_memory, ensure_ascii=False, indent=2)
    
    # 템플릿에 run_memory 추가 (HumanMessage로 직접 전달되므로 이스케이프 불필요)
    formatted_input = f"{human_template}\n\n현재 run_memory:\n{run_memory_str}"
    
    return formatted_input


def _format_update_run_memory(**kwargs) -> str:
    """
    update-run-memory용 내부 포맷터
    
    Args:
        **kwargs: run_memory 등
    
    Returns:
        포맷팅된 입력 문자열
    """
    run_memory = kwargs.get("run_memory", {})
    return format_update_run_memory_input(run_memory)


# update-run-memory 포맷터 등록
register_input_formatter("update-run-memory", _format_update_run_memory)
