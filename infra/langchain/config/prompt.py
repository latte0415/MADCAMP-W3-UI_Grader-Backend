import os
from typing import Any
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

# config 디렉토리의 상위 디렉토리에서 prompts 디렉토리 찾기
_PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

def get_prompt(
    name: str, 
    input_variables: dict[str, Any] | None = None,
    format_instructions: str | None = None
) -> ChatPromptTemplate:
    """
    prompts/{category}/{name}.txt 파일을 불러와 변수를 채워서 반환합니다.
    
    Args:
        name: 프롬프트 이름
        input_variables: 프롬프트 템플릿에 채울 변수들 (예: {"prompt": "사용자 입력"})
        format_instructions: 출력 형식 지침
    """

    path_system = os.path.join(_PROMPT_DIR, "system", f"{name}.txt")
    path_human = os.path.join(_PROMPT_DIR, "human", f"{name}.txt")

    if not os.path.isfile(path_system):
        raise FileNotFoundError(f"Prompt '{name}' does not exist at {path_system}")
    if not os.path.isfile(path_human):
        raise FileNotFoundError(f"Prompt '{name}' does not exist at {path_human}")

    with open(path_system, encoding="utf-8") as file:
        prompt_system = file.read()
    with open(path_human, encoding="utf-8") as file:
        prompt_human = file.read()
    
    # format_instructions가 있으면 system 프롬프트에 추가
    # ChatPromptTemplate에서 중괄호는 변수로 인식되므로 이스케이프 처리 필요
    if format_instructions:
        escaped_format = format_instructions.replace("{", "{{").replace("}", "}}")
        prompt_system = prompt_system + f"\n\n{escaped_format}"
    
    # ChatPromptTemplate은 템플릿 변수를 직접 처리하므로 미리 format하지 않음
    # 변수는 chain 실행 시 ChatPromptTemplate이 자동으로 처리
    prompt = ChatPromptTemplate.from_messages([
        ("system", prompt_system),
        ("human", prompt_human),
    ])

    return prompt


def get_agent_prompt(
    name: str = "mapping",
    input_variables: dict[str, Any] | None = None
) -> str:
    """
    prompts/agent/{name}.txt 파일을 불러와 변수를 채운 문자열을 반환합니다.
    
    이 함수는 ReAct 프롬프트를 만드는 것이 아니라, 사용자 입력 프롬프트를 생성합니다.
    반환된 문자열은 AgentExecutor의 {"input": "..."} 부분에 전달됩니다.
    
    Args:
        name: 프롬프트 이름 (기본값: "mapping")
        input_variables: 프롬프트 템플릿에 채울 변수들 (예: {"input_prompt": "사용자 입력"})
    
    Returns:
        str: 변수가 채워진 프롬프트 문자열
    """
    path_agent = os.path.join(_PROMPT_DIR, "agent", f"{name}.txt")
    
    if not os.path.isfile(path_agent):
        raise FileNotFoundError(f"Agent prompt '{name}' does not exist at {path_agent}")
    
    with open(path_agent, encoding="utf-8") as file:
        prompt_template = file.read()
    
    # input_variables가 있으면 템플릿에 주입 (예: {input_prompt} -> 실제 값)
    if input_variables:
        prompt = prompt_template.format(**input_variables)
    else:
        prompt = prompt_template
    
    return prompt