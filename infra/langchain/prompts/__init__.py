"""
prompts 폴더: system/human 프롬프트 로드.

- get_human_input(label): human/{label}.txt 내용 반환 (사전 세팅용 input)
- get_agent_prompt(label): Agent용 ChatPromptTemplate (system/{label}.txt 기반)
"""

import os

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

_PROMPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_human_input(label: str) -> str:
    """prompts/human/{label}.txt 내용을 읽어 반환 (사전 세팅용 input 값)."""
    path = os.path.join(_PROMPT_DIR, "human", f"{label}.txt")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Human prompt '{label}' not found at {path}")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def get_agent_prompt(label: str = "chat-test") -> ChatPromptTemplate:
    """
    prompts/system/{label}.txt 를 읽어 Agent용 ChatPromptTemplate을 반환합니다.
    Human 메시지는 {input} 플레이스홀더로 두고, 실제 값은 run_agent에서
    get_human_input(label)으로 읽어 {"input": ...} 으로 전달합니다.

    Args:
        label: 프롬프트 레이블 (파일명). 예: "chat-test", "tool-test"

    Returns:
        ChatPromptTemplate (get_agent용)
    """
    path_system = os.path.join(_PROMPT_DIR, "system", f"{label}.txt")
    system_content = ""
    if os.path.isfile(path_system):
        with open(path_system, encoding="utf-8") as f:
            system_content = f.read().strip()

    return ChatPromptTemplate.from_messages([
        ("system", system_content or "You are a helpful assistant."),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
