"""
Agent 실행 모듈

Infrastructure 레이어: LangChain Agent 실행
Function Calling 방식 사용 (OpenAI Tools Agent)
"""

import os
from typing import Any
from langchain_core.runnables import Runnable
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from infra.langchain.config.llm import get_llm
from infra.langchain.config.executor import ainvoke_runnable
from infra.langchain.config.tools import get_web_search_tools
from infra.langchain.config.prompt import get_agent_prompt
from exceptions import InfrastructureException

# config 디렉토리의 상위 디렉토리에서 prompts 디렉토리 찾기
_PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


def get_agent_prompt_template(label: str = "mapping") -> ChatPromptTemplate:
    """
    Function Calling 방식에 사용할 프롬프트 템플릿을 생성합니다.
    prompts/agent/{label}.txt 파일을 읽어서 시스템 프롬프트로 사용합니다.
    {input_prompt} 변수는 시스템 프롬프트에서 제거하고, 실제 입력은 human 메시지로 전달됩니다.
    
    Args:
        label: 프롬프트 레이블 (기본값: "mapping")
    
    Returns:
        ChatPromptTemplate: 에이전트용 프롬프트 템플릿
    """
    path_agent = os.path.join(_PROMPT_DIR, "agent", f"{label}.txt")
    
    # 파일이 존재하면 읽어서 시스템 프롬프트로 사용
    if os.path.isfile(path_agent):
        with open(path_agent, encoding="utf-8") as file:
            system_prompt = file.read()
        
        # {input_prompt} 변수가 포함된 줄을 제거하거나, 변수 부분만 제거
        # 예: "# 커피\n{input_prompt}" -> "# 커피" 또는 빈 줄로 처리
        lines = system_prompt.split('\n')
        cleaned_lines = []
        skip_next = False
        
        for i, line in enumerate(lines):
            # {input_prompt}만 있는 줄은 제거
            if line.strip() == '{input_prompt}':
                continue
            # {input_prompt}가 포함된 줄에서 변수 부분만 제거
            if '{input_prompt}' in line:
                # "# 커피\n{input_prompt}" 같은 경우 "# 커피" 부분만 남김
                cleaned_line = line.replace('{input_prompt}', '').strip()
                if cleaned_line:  # 남은 내용이 있으면 추가
                    cleaned_lines.append(cleaned_line)
            else:
                cleaned_lines.append(line)
        
        system_prompt = '\n'.join(cleaned_lines).strip()
    else:
        # 파일이 없으면 기본 시스템 프롬프트 사용
        system_prompt = "You are a helpful assistant that can use tools to answer questions. " \
                       "When you have gathered enough information, provide a clear and concise answer."
    
    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])


def get_agent(web_search: bool = False, label: str = "mapping") -> Runnable:
    """
    Function Calling 방식의 Agent를 구성합니다.
    
    Args:
        web_search: 웹 검색 도구 사용 여부
        label: 프롬프트 레이블 (기본값: "mapping", 현재는 사용되지 않지만 호환성을 위해 유지)
    
    Returns:
        AgentExecutor (Runnable)
    """
    llm = get_llm()
    tools = []
    
    # web_search가 True이면 웹 검색 도구 추가
    if web_search:
        tools.extend(get_web_search_tools())
    
    # Function Calling 방식은 도구가 없으면 에이전트를 생성할 수 없음
    if not tools:
        raise ValueError("At least one tool is required for the agent. Set web_search=True to enable web search tools.")
    
    # Function Calling 방식 프롬프트 생성 (label에 맞는 프롬프트 파일 사용)
    prompt = get_agent_prompt_template(label=label)
    
    # OpenAI Tools Agent 생성 (Function Calling 방식)
    agent = create_openai_tools_agent(llm, tools, prompt)
    
    # AgentExecutor 생성 (Runnable이므로 반환 가능)
    # Function Calling 방식은 파싱 에러가 거의 발생하지 않으므로 handle_parsing_errors 불필요
    agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools, 
        verbose=True,
        max_iterations=3,
        max_execution_time=30,
    )
    return agent_executor


async def run_agent(input_prompt: str, web_search: bool = False, label: str = "mapping") -> str:
    """
    Function Calling 방식의 Agent를 실행합니다.
    Infrastructure 레이어: 실행 실패 시 InfrastructureException을 발생시킵니다.
    
    Args:
        input_prompt: 사용자 입력 프롬프트
        web_search: 웹 검색 도구 사용 여부
        label: 프롬프트 레이블 (기본값: "mapping")
                 - prompts/agent/{label}.txt 파일이 시스템 프롬프트로 사용됨
                 - {input_prompt} 변수는 human 메시지에서 채워짐
    
    Returns:
        Agent 실행 결과 (문자열)
    
    Raises:
        InfrastructureException: Agent 실행 실패 시
    """
    try:
        # Agent 생성 (Function Calling 방식)
        # get_agent 내부에서 prompts/agent/{label}.txt를 시스템 프롬프트로 사용
        agent_executor = get_agent(web_search=web_search, label=label)
        
        # prompts/agent/{label}.txt를 읽어서 {input_prompt}를 채운 문자열 생성
        # 이 문자열은 human 메시지로 전달됨
        agent_input_prompt = get_agent_prompt(
            name=label,
            input_variables={"input_prompt": input_prompt}
        )
        
        # AgentExecutor는 {"input": "..."} 형식으로 입력받음
        # Function Calling 방식에서도 동일한 인터페이스 사용
        agent_input = {"input": agent_input_prompt}
        
        result = await ainvoke_runnable(
            chain=agent_executor,
            variables=agent_input,
            step_label="agent"
        )
        
        # AgentExecutor의 출력은 {"output": "..."} 형식이므로 output 추출
        if isinstance(result, dict) and "output" in result:
            return result["output"]
        return str(result)
    except Exception as e:
        # 모든 예외를 InfrastructureException으로 변환
        raise InfrastructureException(f"Agent 실행 실패: {e}") from e