"""
label별 도구 레지스트리.

- get_tools_for_label(label): label에 매핑된 도구 리스트 반환.
- 레지스트리에 없는 label은 calculator_tools로 폴백.
"""
from .calculator import calculator_tools
from .echo import chat_tools
from .run_memory import update_run_memory_tools, filter_action_tools

# label -> tools 리스트
LABEL_TOOLS: dict[str, list] = {
    "chat-test": chat_tools,
    "tool-test": calculator_tools,
    "update-run-memory": update_run_memory_tools,
    "filter-action": filter_action_tools,
    "photo-test": [],  # photo-test는 기본적으로 도구 없음 (필요시 추가 가능)
}

# label -> tool_choice 설정
# "any": 반드시 도구 사용 (강제)
# "auto": LLM이 선택 (기본값)
# "none": 도구 사용 안 함
# 또는 특정 도구 이름: 해당 도구만 사용
LABEL_TOOL_CHOICE: dict[str, str | dict] = {
    "chat-test": "auto",  # chat은 도구 선택적
    "tool-test": "any",    # tool-test는 도구 사용 강제
    "update-run-memory": "any",    # update-run-memory는 도구 사용 강제
    "filter-action": "any",    # filter-action은 도구 사용 강제
    "photo-test": "none",  # photo-test는 도구 사용 안 함 (이미지 분석에 집중)
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


def get_tool_choice_for_label(label: str) -> str | dict | None:
    """
    label에 맞는 tool_choice 설정을 반환합니다.

    Args:
        label: 프롬프트 레이블 (예: "chat-test", "tool-test")

    Returns:
        tool_choice 값 ("any", "auto", "none", 또는 특정 도구 이름/딕셔너리)
        None이면 기본값(LLM이 자동 선택)
    """
    return LABEL_TOOL_CHOICE.get(label, "auto")
