from infra.langchain.runnables.agent import run_agent
from infra.langchain.config.context import set_run_id, set_from_node_id
from typing import Dict, Optional, Any, List
from uuid import UUID
import json

from infra.langchain.runnables.agent import get_agent
from infra.langchain.config.executor import ainvoke_runnable
from infra.langchain.config.context import set_run_id as set_run_id_context
from infra.langchain.prompts import get_human_input, create_human_message_with_image
from utils.llm_result_extractor import format_auxiliary_data_for_input, extract_final_response_result
        

class AiService:
    """AI·에이전트 관련 서비스 (chat, tool-test, photo, run_memory, filter-action)."""

    def __init__(self):
        pass

    async def get_ai_response(self) -> str:
        """chat-test 에이전트 실행. Returns: AI 응답 문자열."""
        result = await run_agent(label="chat-test")
        return str(result)

    async def get_ai_response_with_calculator_tools(self) -> str:
        """tool-test 에이전트 실행 (calculator 도구). Returns: AI 응답 문자열."""
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

    async def filter_input_actions_with_run_memory(
        self,
        input_actions: List[Dict[str, Any]],
        run_id: UUID,
        from_node_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        입력 액션을 run_memory에 저장된 정보를 기반으로 필터링합니다.
        
        Args:
            input_actions: 입력값이 필요한 액션 리스트 (딕셔너리 형태)
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
        
        Returns:
            처리 가능한 액션 리스트 (action_value가 채워진 딕셔너리 형태)
        """
        # context 설정
        set_run_id(run_id)
        set_from_node_id(from_node_id)
        
        # auxiliary_data로 input_actions 전달
        auxiliary_data = {
            "input_actions": json.dumps(input_actions, ensure_ascii=False)
        }
        
        # run_agent를 직접 호출하여 intermediate_steps 확인
        # context 설정 (run_agent 내부에서도 설정하지만 명시적으로 설정)
        set_run_id_context(run_id)
        
        agent_executor = get_agent(label="filter-action", use_vision=False)
        human_input = get_human_input("filter-action")
        
        # auxiliary_data를 human_input에 포함
        human_input += format_auxiliary_data_for_input(auxiliary_data)
        
        result = await ainvoke_runnable(
            runnable=agent_executor,
            variables={"input": human_input},
            step_label="agent",
        )
        
        # LLM 결과에서 final_response 툴의 반환값 추출
        return extract_final_response_result(result)