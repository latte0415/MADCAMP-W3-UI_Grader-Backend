from infra.langchain.runnables.agent import run_agent

class AiService:
    def __init__(self):
        pass

    async def get_ai_response(self) -> str:
        result = await run_agent(label="chat-test")
        return str(result)

    async def get_ai_response_with_calculator_tools(self) -> str:
        result = await run_agent(label="tool-test")
        return str(result)