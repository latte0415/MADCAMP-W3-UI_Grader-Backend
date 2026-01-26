"""pending_actions 서비스"""
from typing import Dict, List, Optional
from uuid import UUID

from repositories import ai_memory_repository


class PendingActionService:
    """Pending Action 관련 비즈니스 로직"""
    
    def __init__(self, ai_memory_repo=None):
        """
        Args:
            ai_memory_repo: AIMemoryRepository 모듈 (기본값: ai_memory_repository)
        """
        self.ai_memory_repo = ai_memory_repo or ai_memory_repository
    
    def create_pending_action(
        self,
        run_id: UUID,
        from_node_id: UUID,
        action: Dict,
        status: str = "pending"
    ) -> Dict:
        """
        pending_actions에 액션을 저장합니다.
        
        Args:
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
            action: 액션 딕셔너리
            status: 상태 (기본값: 'pending')
        
        Returns:
            생성된 pending_action 정보 딕셔너리
        """
        action_value = action.get("action_value", "") or ""
        return self.ai_memory_repo.create_pending_action(
            run_id=run_id,
            from_node_id=from_node_id,
            action_type=action["action_type"],
            action_target=action["action_target"],
            action_value=action_value,
            status=status
        )
    
    def list_pending_actions(
        self,
        run_id: UUID,
        from_node_id: Optional[UUID] = None,
        status: Optional[str] = "pending"
    ) -> List[Dict]:
        """
        pending_actions를 조회합니다.
        
        Args:
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID (선택적)
            status: 필터링할 상태 (기본값: 'pending', None이면 모든 상태)
        
        Returns:
            pending_action 리스트
        """
        return self.ai_memory_repo.list_pending_actions(run_id, from_node_id, status)


# 하위 호환성을 위한 함수 래퍼
_pending_action_service_instance: Optional[PendingActionService] = None


def _get_pending_action_service() -> PendingActionService:
    """싱글톤 PendingActionService 인스턴스 반환"""
    global _pending_action_service_instance
    if _pending_action_service_instance is None:
        _pending_action_service_instance = PendingActionService()
    return _pending_action_service_instance


def create_pending_action(
    run_id: UUID,
    from_node_id: UUID,
    action: Dict,
    status: str = "pending"
) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_pending_action_service().create_pending_action(run_id, from_node_id, action, status)


def list_pending_actions(
    run_id: UUID,
    from_node_id: Optional[UUID] = None,
    status: Optional[str] = "pending"
) -> List[Dict]:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_pending_action_service().list_pending_actions(run_id, from_node_id, status)
