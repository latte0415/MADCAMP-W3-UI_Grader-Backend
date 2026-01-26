"""
Agent 실행 모듈

Infrastructure 레이어: LangChain Agent 실행
Function Calling 방식 사용 (OpenAI Tools Agent)
"""

from langchain_core.runnables import Runnable
from langchain.agents import create_openai_tools_agent, AgentExecutor
from infra.langchain.config.llm import get_llm
from infra.langchain.config.executor import ainvoke_runnable
from infra.langchain.prompts import get_human_input, get_agent_prompt
from infra.langchain.tools import get_tools_for_label, get_tool_choice_for_label


def get_agent(label: str = "chat-test") -> Runnable:
    llm = get_llm()
    tools = get_tools_for_label(label)
    tool_choice = get_tool_choice_for_label(label)

    # tool_choice가 설정되어 있으면 LLM에 bind
    if tool_choice and tool_choice != "auto":
        llm = llm.bind_tools(tools, tool_choice=tool_choice)

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