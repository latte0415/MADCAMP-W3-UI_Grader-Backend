from infra.langchain.runnables.agent import run_agent
from typing import Dict, Optional, Any
from uuid import UUID

class AiService:
    def __init__(self):
        pass

    async def get_ai_response(self) -> str:
        result = await run_agent(label="chat-test")
        return str(result)

    async def get_ai_response_with_calculator_tools(self) -> str:
        result = await run_agent(label="tool-test")
        return str(result)

    async def get_ai_response_with_photo(
        self,
        image_base64: str,
        auxiliary_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        이미지와 보조 자료를 포함하여 AI 응답을 받습니다.
        
        Args:
            image_base64: base64로 인코딩된 이미지
            auxiliary_data: 보조 자료 딕셔너리 (사용자가 인지할 수 있는 정보만)
        
        Returns:
            AI 응답 문자열
        """
        result = await run_agent(
            label="photo-test",
            image_base64=image_base64,
            auxiliary_data=auxiliary_data
        )
        return str(result)

    async def update_run_memory_with_ai(
        self,
        image_base64: str,
        run_id: UUID,
        auxiliary_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        이미지와 run_id를 포함하여 run_memory를 업데이트합니다.
        
        Args:
            image_base64: base64로 인코딩된 이미지
            run_id: run_id
            auxiliary_data: 보조 자료 딕셔너리 (사용자가 인지할 수 있는 정보만)
        
        Returns:
            AI 응답 문자열
        """
        result = await run_agent(
            label="update-run-memory",
            image_base64=image_base64,
            auxiliary_data=auxiliary_data,
            run_id=run_id
        )
        return str(result)