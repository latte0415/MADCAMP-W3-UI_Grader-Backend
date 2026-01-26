"""
label별 도구 레지스트리.

- get_tools_for_label(label): label에 매핑된 도구 리스트 반환.
- 레지스트리에 없는 label은 calculator_tools로 폴백.
"""
from .calculator import calculator_tools
from .echo import chat_tools

# label -> tools 리스트
LABEL_TOOLS: dict[str, list] = {
    "chat-test": chat_tools,
    "tool-test": calculator_tools,
}


def get_tools_for_label(label: str) -> list:
    """
    label에 맞는 도구 리스트를 반환합니다.

    Args:
        label: 프롬프트 레이블 (예: "chat-test", "tool-test")

    Returns:
        BaseTool 리스트 (최소 1개)
    """
    tools = LABEL_TOOLS.get(label, calculator_tools)
    return tools
