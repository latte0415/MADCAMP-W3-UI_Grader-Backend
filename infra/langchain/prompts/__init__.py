"""
prompts 폴더: system/human 프롬프트 로드.

- get_human_input(label): human/{label}.txt 내용 반환 (사전 세팅용 input)
- get_system_content(label): system/{label}.txt 내용 반환
- get_agent_prompt(label): Agent용 ChatPromptTemplate (system/{label}.txt 기반, agent_scratchpad 포함)
- get_chain_prompt(label): Chain용 ChatPromptTemplate (system/{label}.txt 기반, agent_scratchpad 없음)
- create_human_message_with_image(label, image_base64, auxiliary_data): 이미지 포함 human 메시지 생성
"""

import os
from typing import Optional, Dict, Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage

_PROMPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_human_input(label: str) -> str:
    """prompts/human/{label}.txt 내용을 읽어 반환 (사전 세팅용 input 값)."""
    path = os.path.join(_PROMPT_DIR, "human", f"{label}.txt")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Human prompt '{label}' not found at {path}")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def create_human_message_with_image(
    label: str,
    image_base64: str,
    auxiliary_data: Optional[Dict[str, Any]] = None
) -> HumanMessage:
    """
    이미지와 보조 자료를 포함한 HumanMessage를 생성합니다.
    
    Args:
        label: 프롬프트 레이블
        image_base64: base64로 인코딩된 이미지 (data:image/jpeg;base64, 접두사 포함 또는 미포함)
        auxiliary_data: 보조 자료 딕셔너리 (사용자가 인지할 수 있는 정보만)
    
    Returns:
        HumanMessage 인스턴스
    """
    text_prompt = get_human_input(label)
    
    # 보조 자료가 있으면 텍스트에 추가
    if auxiliary_data:
        auxiliary_text = "\n\n보조 정보:\n"
        for key, value in auxiliary_data.items():
            auxiliary_text += f"- {key}: {value}\n"
        text_prompt += auxiliary_text
    
    # base64 이미지 URL 형식으로 변환
    if not image_base64.startswith("data:image"):
        # MIME 타입 추정 (일반적으로 jpeg로 가정)
        image_url = f"data:image/jpeg;base64,{image_base64}"
    else:
        image_url = image_base64
    
    # 메시지 content를 리스트로 구성 (텍스트 + 이미지)
    content = [
        {"type": "text", "text": text_prompt},
        {
            "type": "image_url",
            "image_url": {"url": image_url}
        }
    ]
    
    return HumanMessage(content=content)


def get_system_content(label: str) -> str:
    """
    prompts/system/{label}.txt 내용을 읽어 반환합니다.
    
    Args:
        label: 프롬프트 레이블 (파일명)
    
    Returns:
        system 프롬프트 내용 (파일이 없으면 빈 문자열)
    """
    path_system = os.path.join(_PROMPT_DIR, "system", f"{label}.txt")
    if os.path.isfile(path_system):
        with open(path_system, encoding="utf-8") as f:
            return f.read().strip()
    return ""


def get_agent_prompt(label: str = "chat-test") -> ChatPromptTemplate:
    """
    prompts/system/{label}.txt 를 읽어 Agent용 ChatPromptTemplate을 반환합니다.
    Human 메시지는 {input} 플레이스홀더로 두고, 실제 값은 run_agent에서
    get_human_input(label)으로 읽어 {"input": ...} 으로 전달합니다.

    Args:
        label: 프롬프트 레이블 (파일명). 예: "chat-test", "tool-test"

    Returns:
        ChatPromptTemplate (get_agent용, agent_scratchpad 포함)
    """
    system_content = get_system_content(label)
    
    return ChatPromptTemplate.from_messages([
        ("system", system_content or "You are a helpful assistant."),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])


def get_chain_prompt(label: str = "filter-action") -> ChatPromptTemplate:
    """
    prompts/system/{label}.txt 를 읽어 Chain용 ChatPromptTemplate을 반환합니다.
    Agent용과 달리 agent_scratchpad가 없습니다.
    
    Human 메시지는 {input} 플레이스홀더로 두고, 실제 값은 run_chain에서
    get_human_input(label)으로 읽어 {"input": ...} 으로 전달합니다.

    Args:
        label: 프롬프트 레이블 (파일명). 예: "filter-action"

    Returns:
        ChatPromptTemplate (get_chain용, agent_scratchpad 없음)
    """
    system_content = get_system_content(label)
    
    return ChatPromptTemplate.from_messages([
        ("system", system_content or "You are a helpful assistant."),
        ("human", "{input}"),
    ])
