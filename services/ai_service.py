# 레거시: agent 관련 import (다른 메서드에서 사용)
from infra.langchain.runnables.legacy.agent import run_agent
from infra.langchain.config.context import set_run_id, set_from_node_id
from typing import Dict, Optional, Any, List
from uuid import UUID
import json

from infra.langchain.runnables.chain import run_chain
from infra.langchain.config.context import set_run_id as set_run_id_context
from infra.langchain.prompts import create_human_message_with_image
        
from repositories.ai_memory_repository import view_run_memory
from services.pending_action_service import PendingActionService
from schemas.filter_action import FilterActionOutput

class AiService:
    """AI·체인 관련 서비스 (chat, tool-test, photo, run_memory는 레거시 agent 사용, filter-action은 chain 사용)."""

    def __init__(self):
        pass

    # ============================================
    # 레거시: Agent 기반 메서드들 (향후 chain으로 마이그레이션 예정)
    # ============================================
    
    async def get_ai_response(self) -> str:
        """[레거시] chat-test 에이전트 실행. Returns: AI 응답 문자열."""
        result = await run_agent(label="chat-test")
        return str(result)

    async def get_ai_response_with_calculator_tools(self) -> str:
        """[레거시] tool-test 에이전트 실행 (calculator 도구). Returns: AI 응답 문자열."""
        result = await run_agent(label="tool-test")
        return str(result)

    async def get_ai_response_with_photo(
        self,
        image_base64: str,
        auxiliary_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        [레거시] 이미지와 보조 자료를 포함하여 AI 응답을 받습니다.
        
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
        [레거시] 이미지와 run_id를 포함하여 run_memory를 업데이트합니다.
        
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
        
        # 1. pending action 조회
        # pending_action_service = PendingActionService()
        # pending_actions = pending_action_service.list_pending_actions(
        #     run_id=run_id,
        #     from_node_id=from_node_id,
        #     status="pending"
        # )
        
        # 2. run_memory 조회
        run_memory_data = view_run_memory(run_id)
        run_memory_content = run_memory_data.get("content", {}) if run_memory_data else {}
        
        # 3. chain에 input_actions와 run_memory 전달
        result = await run_chain(
            label="filter-action",
            input_actions=input_actions,
            run_memory=run_memory_content,
            use_vision=False
        )
        
        # 4. chain 결과에서 처리 가능한 액션 추출
        if isinstance(result, FilterActionOutput):
            # Pydantic 모델을 dict로 변환
            processable_actions = [action.model_dump(exclude_none=False) for action in result.actions]
        elif isinstance(result, dict) and "actions" in result:
            processable_actions = result["actions"]
        else:
            processable_actions = []
        
        # 5. 처리 불가한 액션 식별 및 pending action에 삽입
        processable_action_keys = set()
        for action in processable_actions:
            # 액션을 고유하게 식별하기 위한 키 생성
            key = (
                action.get("action_type", ""),
                action.get("action_target", ""),
                action.get("selector", ""),
                action.get("role", ""),
                action.get("name", "")
            )
            processable_action_keys.add(key)
        
        # input_actions 중 처리 불가한 액션 찾기
        for action in input_actions:
            # is_filled가 true인 액션은 무시
            if action.get("is_filled", False):
                continue
            
            # 액션을 고유하게 식별하기 위한 키 생성
            action_key = (
                action.get("action_type", ""),
                action.get("action_target", ""),
                action.get("selector", ""),
                action.get("role", ""),
                action.get("name", "")
            )
            
            # 처리 가능한 액션에 포함되지 않은 경우 pending action에 삽입
            if action_key not in processable_action_keys:
                try:
                    pending_action_service = PendingActionService()
                    pending_action_service.create_pending_action(
                        run_id=run_id,
                        from_node_id=from_node_id,
                        action=action,
                        status="pending"
                    )
                except Exception as e:
                    # pending action 생성 실패는 로그만 남기고 계속 진행
                    print(f"[filter_input_actions_with_run_memory] pending action 생성 실패: {e}")
        
        # 6. 적절한 입력값이 있는 액션만 반환
        return processable_actions
    
    async def filter_input_action(
        self,
        input_action: Dict[str, Any],
        run_id: UUID,
        from_node_id: UUID
    ) -> Dict[str, Any]:
        """
        단일 입력 액션을 필터링합니다 (filter_input_actions_with_run_memory의 래퍼).
        
        Args:
            input_action: 입력값이 필요한 단일 액션 (딕셔너리 형태)
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
        
        Returns:
            처리 가능한 액션 (action_value가 채워진 딕셔너리 형태) 또는 빈 딕셔너리
        """
        results = await self.filter_input_actions_with_run_memory(
            input_actions=[input_action],
            run_id=run_id,
            from_node_id=from_node_id
        )
        return results[0] if results else {}