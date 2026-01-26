"""
Chain 실행 모듈

Infrastructure 레이어: LangChain Chain 실행
LLM Chain 방식 사용 (Prompt → LLM → OutputParser)
"""

from typing import Optional, Dict, Any
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers import PydanticOutputParser
from infra.langchain.config.llm import get_llm
from infra.langchain.config.executor import ainvoke_runnable
from infra.langchain.prompts import get_human_input, get_agent_prompt
from infra.langchain.config.parser import get_parser
import json


def get_chain(label: str = "filter-action", use_vision: bool = False) -> Runnable:
    """
    Chain 인스턴스를 생성합니다.
    
    Args:
        label: 프롬프트 레이블
        use_vision: Vision 모델 사용 여부
    
    Returns:
        LangChain Runnable Chain
    """
    # Vision이 필요한 경우 gpt-4o 사용
    model = "gpt-4o" if use_vision else "gpt-4o-mini"
    llm = get_llm(model=model)
    
    # 프롬프트 생성 (chain용 - agent_scratchpad 없음)
    import os
    from langchain_core.prompts import ChatPromptTemplate
    
    # prompts 폴더는 infra/langchain/prompts에 있음
    # __file__ = infra/langchain/runnables/chain.py
    # dirname(dirname(__file__)) = infra/langchain
    _PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    path_system = os.path.join(_PROMPT_DIR, "system", f"{label}.txt")
    system_content = ""
    if os.path.isfile(path_system):
        with open(path_system, encoding="utf-8") as f:
            system_content = f.read().strip()
    # Chain용 프롬프트 (agent_scratchpad 없음)
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_content),
        ("human", "{input}"),
    ])
    
    # Parser 가져오기 (있는 경우)
    parser = get_parser(label)
    
    # Chain 구성: Prompt → LLM → (Parser)
    if parser:
        chain = prompt | llm | parser
    else:
        # Parser가 없으면 LLM만 사용
        chain = prompt | llm
    
    return chain


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


async def run_chain(
    label: str = "filter-action",
    variables: Optional[Dict[str, Any]] = None,
    use_vision: bool = False,
    input_actions: Optional[list[Dict[str, Any]]] = None,
    run_memory: Optional[Dict[str, Any]] = None
) -> Any:
    """
    Chain을 실행합니다.
    
    Args:
        label: 프롬프트 레이블
        variables: Chain에 전달할 입력 변수 (예: {"input": "..."})
        use_vision: Vision 모델 사용 여부
        input_actions: filter-action용 입력 액션 리스트 (label이 "filter-action"일 때)
        run_memory: filter-action용 run_memory (label이 "filter-action"일 때)
    
    Returns:
        Chain 실행 결과
    """
    try:
        chain = get_chain(label=label, use_vision=use_vision)
        
        # filter-action의 경우 특별 처리
        if label == "filter-action" and input_actions is not None and run_memory is not None:
            formatted_input = format_filter_action_input(input_actions, run_memory)
            variables = {"input": formatted_input}
        elif variables is None:
            # variables가 없으면 human_input 사용
            human_input = get_human_input(label)
            variables = {"input": human_input}
        
        result = await ainvoke_runnable(
            runnable=chain,
            variables=variables,
            step_label=f"chain-{label}",
        )
        
        return result
    except Exception as e:
        # 모든 예외를 RuntimeError로 변환
        raise RuntimeError(f"Chain 실행 실패: {e}") from e
