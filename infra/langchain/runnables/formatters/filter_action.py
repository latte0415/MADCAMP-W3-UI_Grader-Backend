"""
filter-action chain용 입력 포맷터
"""

from typing import Dict, Any
import json
from infra.langchain.prompts import get_human_input
from . import register_input_formatter


def format_filter_action_input(
    input_actions: list[Dict[str, Any]],
    run_memory: Dict[str, Any]
) -> str:
    """
    filter-action chain용 입력 포맷팅
    
    Args:
        input_actions: 입력 액션 리스트
        run_memory: run_memory의 content 딕셔너리
    
    Returns:
        포맷팅된 human input 문자열
    """
    human_template = get_human_input("filter-action")
    
    # run_memory를 JSON 문자열로 변환
    run_memory_str = json.dumps(run_memory, ensure_ascii=False, indent=2)
    
    # input_actions를 JSON 문자열로 변환
    input_actions_str = json.dumps(input_actions, ensure_ascii=False, indent=2)
    
    # 템플릿에 값 채우기
    formatted_input = human_template.format(
        run_memory=run_memory_str,
        input_actions=input_actions_str
    )
    
    return formatted_input


def _format_filter_action(**kwargs) -> str:
    """
    filter-action용 내부 포맷터
    
    Args:
        **kwargs: input_actions, run_memory 등
    
    Returns:
        포맷팅된 입력 문자열
    """
    input_actions = kwargs.get("input_actions")
    run_memory = kwargs.get("run_memory", {})
    if input_actions is None:
        raise ValueError("input_actions is required for filter-action")
    return format_filter_action_input(input_actions, run_memory)


# filter-action 포맷터 자동 등록
register_input_formatter("filter-action", _format_filter_action)
