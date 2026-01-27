"""
guess-intent chain용 입력 포맷터
"""
from typing import Dict, Any
from infra.langchain.prompts import get_human_input
from . import register_input_formatter


def format_guess_intent_input(
    from_node: Dict[str, Any],
    to_node: Dict[str, Any],
    edge: Dict[str, Any]
) -> str:
    """
    guess-intent chain용 입력 포맷팅
    
    Args:
        from_node: 시작 노드 정보 딕셔너리
        to_node: 도착 노드 정보 딕셔너리
        edge: 엣지 정보 딕셔너리
    
    Returns:
        포맷팅된 human input 문자열
    """
    human_template = get_human_input("guess-intent")
    
    # 템플릿에 값 채우기
    formatted_input = human_template.format(
        from_node_url=from_node.get("url", ""),
        from_node_url_normalized=from_node.get("url_normalized", ""),
        to_node_url=to_node.get("url", ""),
        to_node_url_normalized=to_node.get("url_normalized", ""),
        action_type=edge.get("action_type", ""),
        action_target=edge.get("action_target", ""),
        action_value=edge.get("action_value", "") or ""
    )
    
    return formatted_input


def _format_guess_intent(**kwargs) -> str:
    """
    guess-intent용 내부 포맷터
    
    Args:
        **kwargs: from_node, to_node, edge 등
    
    Returns:
        포맷팅된 입력 문자열
    """
    from_node = kwargs.get("from_node")
    to_node = kwargs.get("to_node")
    edge = kwargs.get("edge")
    
    if from_node is None:
        raise ValueError("from_node is required for guess-intent")
    if to_node is None:
        raise ValueError("to_node is required for guess-intent")
    if edge is None:
        raise ValueError("edge is required for guess-intent")
    
    return format_guess_intent_input(from_node, to_node, edge)


# guess-intent 포맷터 자동 등록
register_input_formatter("guess-intent", _format_guess_intent)
