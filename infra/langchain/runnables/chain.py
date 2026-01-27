"""
Chain 실행 모듈

Infrastructure 레이어: LangChain Chain 실행
LLM Chain 방식 사용 (Prompt → LLM → OutputParser)

주요 함수:
- get_chain(label, use_vision): Chain 인스턴스 생성
- run_chain(label, variables, ...): Chain 실행
"""

from typing import Optional, Dict, Any
from langchain_core.runnables import Runnable
from langchain_core.messages import HumanMessage
from infra.langchain.config.llm import get_llm
from infra.langchain.config.executor import ainvoke_runnable
from infra.langchain.prompts import get_human_input, get_chain_prompt, create_human_message_with_image
from infra.langchain.config.parser import get_parser
from infra.langchain.runnables.formatters import get_input_formatter, has_input_formatter

# formatters 모듈 import (포맷터 자동 등록을 위해)
from infra.langchain.runnables.formatters import filter_action  # noqa: F401
from infra.langchain.runnables.formatters import update_run_memory  # noqa: F401
from infra.langchain.runnables.formatters import process_pending_actions  # noqa: F401
from infra.langchain.runnables.formatters import guess_intent  # noqa: F401


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
    
    # Parser 가져오기 (있는 경우)
    parser = get_parser(label)
    
    # Chain용 프롬프트 생성 (agent_scratchpad 없음)
    # Parser가 있으면 format_instructions를 시스템 프롬프트에 추가
    if parser:
        from infra.langchain.prompts import get_system_content
        from langchain_core.prompts import ChatPromptTemplate
        
        system_content = get_system_content(label)
        format_instructions = parser.get_format_instructions()
        
        # format_instructions의 중괄호를 이스케이프 (LangChain 템플릿 변수로 해석되지 않도록)
        escaped_format_instructions = format_instructions.replace("{", "{{").replace("}", "}}")
        
        # format_instructions를 시스템 프롬프트에 추가
        full_system_content = f"{system_content or 'You are a helpful assistant.'}\n\n{escaped_format_instructions}"
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", full_system_content),
            ("human", "{input}"),
        ])
    else:
        prompt = get_chain_prompt(label=label)
    
    # Chain 구성: Prompt → LLM → (Parser)
    if parser:
        chain = prompt | llm | parser
    else:
        # Parser가 없으면 LLM만 사용
        chain = prompt | llm
    
    return chain


async def run_chain(
    label: str = "filter-action",
    variables: Optional[Dict[str, Any]] = None,
    use_vision: bool = False,
    image_base64: Optional[str] = None,
    auxiliary_data: Optional[Dict[str, Any]] = None,
    **kwargs: Any
) -> Any:
    """
    Chain을 실행합니다.
    
    Args:
        label: 프롬프트 레이블
        variables: Chain에 전달할 입력 변수 (예: {"input": "..."})
                   None이면 human_input을 사용하거나 등록된 포맷터를 사용
        use_vision: Vision 모델 사용 여부 (이미지가 있으면 자동으로 True)
        image_base64: base64로 인코딩된 이미지 (선택적)
        auxiliary_data: 보조 자료 딕셔너리 (이미지와 함께 사용, 선택적)
        **kwargs: label별 특수 파라미터 (예: filter-action의 경우 input_actions, run_memory)
    
    Returns:
        Chain 실행 결과
    
    Examples:
        # 기본 사용 (human_input 사용)
        result = await run_chain(label="some-label")
        
        # variables 직접 전달
        result = await run_chain(label="some-label", variables={"input": "..."})
        
        # filter-action (등록된 포맷터 사용)
        result = await run_chain(
            label="filter-action",
            input_actions=[...],
            run_memory={...}
        )
        
        # 이미지 포함
        result = await run_chain(
            label="photo-test",
            image_base64="...",
            auxiliary_data={...}
        )
    """
    try:
        # 이미지가 있으면 vision 모델 사용
        if image_base64:
            use_vision = True
        
        chain = get_chain(label=label, use_vision=use_vision)
        
        # variables가 없으면 입력 생성
        if variables is None:
            # 이미지가 있는 경우 특별 처리
            if image_base64:
                # 등록된 포맷터가 있으면 사용 (예: update-run-memory)
                if has_input_formatter(label):
                    formatter = get_input_formatter(label)
                    formatted_text = formatter(**kwargs)
                else:
                    # 포맷터가 없으면 기본 human_input 사용
                    formatted_text = get_human_input(label)
                
                # 보조 자료가 있으면 텍스트에 추가
                if auxiliary_data:
                    auxiliary_text = "\n\n보조 정보:\n"
                    for key, value in auxiliary_data.items():
                        auxiliary_text += f"- {key}: {value}\n"
                    formatted_text += auxiliary_text
                
                # 이미지가 포함된 HumanMessage 생성
                from langchain_core.messages import HumanMessage
                
                # base64 이미지 URL 형식으로 변환
                if not image_base64.startswith("data:image"):
                    image_url = f"data:image/jpeg;base64,{image_base64}"
                else:
                    image_url = image_base64
                
                # 메시지 content를 리스트로 구성 (텍스트 + 이미지)
                content = [
                    {"type": "text", "text": formatted_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url}
                    }
                ]
                human_message = HumanMessage(content=content)
                
                # 이미지가 포함된 메시지는 메시지 리스트로 전달
                # 프롬프트 템플릿의 {input} 플레이스홀더 대신 메시지를 직접 사용
                from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
                from infra.langchain.prompts import get_system_content
                
                system_content = get_system_content(label)
                
                # Parser가 있으면 format_instructions 추가
                parser = get_parser(label)
                if parser:
                    format_instructions = parser.get_format_instructions()
                    # format_instructions의 중괄호를 이스케이프 (LangChain 템플릿 변수로 해석되지 않도록)
                    escaped_format_instructions = format_instructions.replace("{", "{{").replace("}", "}}")
                    full_system_content = f"{system_content or 'You are a helpful assistant.'}\n\n{escaped_format_instructions}"
                else:
                    full_system_content = system_content or "You are a helpful assistant."
                
                # 이미지용 프롬프트 템플릿 생성 (메시지 직접 전달)
                image_prompt = ChatPromptTemplate.from_messages([
                    ("system", full_system_content),
                    MessagesPlaceholder(variable_name="messages"),
                ])
                
                # 이미지용 chain 재구성 (LLM과 Parser 재사용)
                model = "gpt-4o"  # 이미지가 있으면 항상 gpt-4o 사용
                llm = get_llm(model=model)
                parser = get_parser(label)
                
                if parser:
                    image_chain = image_prompt | llm | parser
                else:
                    image_chain = image_prompt | llm
                
                result = await ainvoke_runnable(
                    runnable=image_chain,
                    variables={"messages": [human_message]},
                    step_label=f"chain-{label}",
                )
                return result
            # 등록된 포맷터가 있으면 사용
            elif has_input_formatter(label):
                formatter = get_input_formatter(label)
                formatted_input = formatter(**kwargs)
                variables = {"input": formatted_input}
            else:
                # 기본: human_input 사용
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
