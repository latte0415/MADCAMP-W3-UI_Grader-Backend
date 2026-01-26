"""
Agent 실행 모듈

Infrastructure 레이어: LangChain Agent 실행
Function Calling 방식 사용 (OpenAI Tools Agent)
"""

import os

from langchain_core.runnables import Runnable
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from infra.langchain.config.llm import get_llm
from infra.langchain.config.executor import ainvoke_runnable
from infra.langchain.tools import get_tools_for_label

# runnables 상위에서 prompts 디렉토리 찾기
_PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


def _get_human_input(label: str) -> str:
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
    prompts/human/{label}.txt 내용을 읽어 {"input": ...} 으로 전달합니다.

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


def get_agent(label: str = "chat-test") -> Runnable:
    llm = get_llm()
    tools = get_tools_for_label(label)

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


async def run_agent(label: str = "chat-test") -> str:
    try:
        agent_executor = get_agent(label=label)
        human_input = _get_human_input(label)

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