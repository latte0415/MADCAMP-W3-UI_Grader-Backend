"""
Agent 실행 모듈

Infrastructure 레이어: LangChain Agent 실행
Function Calling 방식 사용 (OpenAI Tools Agent)
"""

from typing import Optional, Dict, Any
from uuid import UUID
from langchain_core.runnables import Runnable
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from infra.langchain.config.llm import get_llm
from infra.langchain.config.executor import ainvoke_runnable
from infra.langchain.config.context import set_run_id
from infra.langchain.prompts import (
    get_human_input,
    get_agent_prompt,
    create_human_message_with_image
)
from infra.langchain.tools import get_tools_for_label, get_tool_choice_for_label


def get_agent(label: str = "chat-test", use_vision: bool = False) -> Runnable:
    """
    Agent 인스턴스를 생성합니다.
    
    Args:
        label: 프롬프트 레이블
        use_vision: Vision 모델 사용 여부
    """
    # Vision이 필요한 경우 gpt-4o 사용
    model = "gpt-4o" if use_vision else "gpt-4o-mini"
    llm = get_llm(model=model)
    tools = get_tools_for_label(label)
    tool_choice = get_tool_choice_for_label(label)

    # tool_choice가 설정되어 있으면 LLM에 bind
    # "none"이면 도구를 bind하지 않음
    if tool_choice == "none":
        pass  # 도구 사용 안 함
    elif tool_choice and tool_choice != "auto":
        llm = llm.bind_tools(tools, tool_choice=tool_choice)
    elif tools:
        # tools가 있고 tool_choice가 "auto"이면 기본적으로 bind
        llm = llm.bind_tools(tools)

    prompt = get_agent_prompt(label=label)
    agent = create_openai_tools_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=3,
        max_execution_time=30,
        return_intermediate_steps=True,  # final_response tool 호출 확인용
    )
    return agent_executor


async def run_agent(
    label: str = "chat-test",
    image_base64: Optional[str] = None,
    auxiliary_data: Optional[Dict[str, Any]] = None,
    run_id: Optional[UUID] = None
) -> str:
    """
    Agent를 실행합니다.
    
    Args:
        label: 프롬프트 레이블
        image_base64: base64로 인코딩된 이미지 (선택적)
        auxiliary_data: 보조 자료 딕셔너리 (선택적, 사용자가 인지할 수 있는 정보만)
        run_id: run_id (선택적, run_memory 도구 사용 시 필요)
    
    Returns:
        Agent 실행 결과 문자열
    """
    try:
        # run_id가 제공되면 context에 설정
        if run_id:
            set_run_id(run_id)
        
        use_vision = image_base64 is not None
        agent_executor = get_agent(label=label, use_vision=use_vision)
        
        if image_base64:
            # 이미지가 있는 경우 HumanMessage 직접 생성
            human_message = create_human_message_with_image(
                label=label,
                image_base64=image_base64,
                auxiliary_data=auxiliary_data
            )
            
            # 프롬프트를 가져와서 system 내용 추출 (custom_prompt용)
            prompt_template = get_agent_prompt(label=label)
            
            # AgentExecutor는 내부적으로 프롬프트를 사용하므로,
            # 메시지를 직접 전달하기 위해 Runnable을 직접 invoke
            # 하지만 AgentExecutor는 variables를 기대하므로, 
            # 프롬프트를 수정하여 이미지를 포함시켜야 함
            # 임시 해결책: 프롬프트를 동적으로 수정
            from langchain_core.messages import SystemMessage
            system_content = prompt_template.messages[0].content if hasattr(prompt_template.messages[0], 'content') else ""
            
            # 새로운 프롬프트 생성 (이미지 포함)
            custom_prompt = ChatPromptTemplate.from_messages([
                ("system", system_content),
                MessagesPlaceholder(variable_name="human_message"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])
            
            # Agent를 다시 생성 (커스텀 프롬프트 사용)
            model = "gpt-4o"
            llm = get_llm(model=model)
            tools = get_tools_for_label(label)
            tool_choice = get_tool_choice_for_label(label)
            # tool_choice가 "none"이 아니고 "auto"가 아닐 때만 bind_tools
            if tool_choice and tool_choice != "auto" and tool_choice != "none":
                llm = llm.bind_tools(tools, tool_choice=tool_choice)
            elif tool_choice != "none" and tools:
                # tools가 있고 tool_choice가 "none"이 아니면 기본적으로 bind
                llm = llm.bind_tools(tools)
            
            agent = create_openai_tools_agent(llm, tools, custom_prompt)
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                max_iterations=3,
                max_execution_time=30,
                return_intermediate_steps=True,
            )
            
            # 메시지 직접 전달
            result = await ainvoke_runnable(
                runnable=agent_executor,
                variables={"human_message": [human_message]},
                step_label="agent",
            )
        else:
            # 기존 방식 (텍스트만)
            human_input = get_human_input(label)
            result = await ainvoke_runnable(
                runnable=agent_executor,
                variables={"input": human_input},
                step_label="agent",
            )
        
        # final_response tool이 호출되었는지 확인
        if isinstance(result, dict):
            # return_intermediate_steps=True이면 intermediate_steps에 tool 호출 기록이 있음
            if "intermediate_steps" in result:
                for action, observation in result["intermediate_steps"]:
                    # action.tool이 "final_response"인지 확인
                    if hasattr(action, "tool") and action.tool == "final_response":
                        # observation이 dict이고 "response" 키가 있으면 사용
                        if isinstance(observation, dict) and "response" in observation:
                            return str(observation["response"])
            
            # final_response가 없으면 일반 output 반환
            if "output" in result:
                return result["output"]
        
        return str(result)
    except Exception as e:
        # 모든 예외를 RuntimeError로 변환
        raise RuntimeError(f"Agent 실행 실패: {e}") from e