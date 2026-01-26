"""
LangChain 스켈레톤 예시

요청한 2가지 형태만 최소 구성으로 제공:
1) chat 형태 기본 호출
2) tool을 직접 주입하는 agent 호출
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import AgentExecutor, create_openai_tools_agent
from infra.langchain.config.llm import get_llm
from infra.langchain.config.executor import ainvoke_runnable


async def run_basic_chat(input_text: str, system_prompt: str = "You are a helpful assistant.") -> str:
    """
    Chat 형태 기본 호출 스켈레톤.
    - system/human 메시지 2개로 최소 구성
    """
    try:
        llm = get_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        chain = prompt | llm
        result = await ainvoke_runnable(
            chain=chain,
            variables={"input": input_text},
            step_label="basic_chat",
        )
        return str(result)
    except Exception as e:
        raise RuntimeError(f"basic chat 실행 실패: {e}") from e


async def run_agent_with_tools(input_text: str, tools: list[Any]) -> str:
    """
    Tool을 직접 생성해서 주입하는 Agent 호출 스켈레톤.
    - tools는 호출하는 쪽에서 직접 생성해서 전달
    """
    if not tools:
        raise ValueError("tools 파라미터는 비어 있을 수 없습니다.")

    try:
        llm = get_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that can use tools."),
            ("human", "{input}"),
            ("assistant", "용도에 맞는 도구를 선택해 사용하세요."),
        ])

        agent = create_openai_tools_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=3)

        result = await ainvoke_runnable(
            chain=executor,
            variables={"input": input_text},
            step_label="agent_with_tools",
        )
        if isinstance(result, dict) and "output" in result:
            return result["output"]
        return str(result)
    except Exception as e:
        raise RuntimeError(f"agent 실행 실패: {e}") from e
