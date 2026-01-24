"""
Chain 실행 모듈

Infrastructure 레이어: LangChain Chain 실행
"""

from typing import Any
from langchain_core.runnables import Runnable
from infra.langchain.config.llm import get_llm
from infra.langchain.config.prompt import get_prompt
from infra.langchain.config.executor import ainvoke_runnable
from infra.langchain.config.parser import get_parser
from exceptions import ChainExecutionException


def get_chain(label: str = "test", input_variables: dict[str, Any] | None = None) -> Runnable:
    """
    Label에 해당하는 체인을 구성합니다.
    
    Args:
        label: 체인 레이블
        input_variables: 프롬프트에 채울 변수들
    
    Returns:
        Runnable: 구성된 Chain
    """
    llm = get_llm()
    parser = get_parser(label)
    
    if parser:
        format_instructions = parser.get_format_instructions()
        prompt = get_prompt(label, input_variables, format_instructions)
        return prompt | llm | parser
    else:
        prompt = get_prompt(label, input_variables)
        return prompt | llm

async def run_chain(
    label: str = "test", 
    input_variables: dict[str, Any] = {}
) -> Any:
    """
    체인을 실행합니다.
    Infrastructure 레이어: 실행 실패 시 ChainExecutionException을 발생시킵니다.
    
    Args:
        label: 체인 레이블
        input_variables: 체인에 전달할 입력 변수
    
    Returns:
        체인 실행 결과
    
    Raises:
        ChainExecutionException: 체인 실행 실패 시
    """
    try:
        sequence = get_chain(label, input_variables)
        result = await ainvoke_runnable(
            chain=sequence,
            variables=input_variables,
            step_label=label
        )
        return result
    except Exception as e:
        # 모든 예외를 ChainExecutionException으로 변환 (InfrastructureException 포함)
        raise ChainExecutionException(f"체인 실행 실패 (label: {label}): {e}") from e