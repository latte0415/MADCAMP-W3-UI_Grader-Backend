"""AI Memory Repository
런 사이클 내 메모리와 pending_actions를 관리하는 리포지토리
"""
from typing import Dict, List, Optional
from uuid import UUID

from infra.supabase import get_client


# ============================================
# Run Memory 관련 메서드
# ============================================

def get_run_memory(run_id: UUID) -> Optional[Dict]:
    """
    run_id로 run_memory 조회
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        run_memory 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("run_memory").select("*").eq("run_id", str(run_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def create_run_memory(run_id: UUID, content: Dict) -> Dict:
    """
    run_memory 생성
    
    Args:
        run_id: 탐색 세션 ID
        content: JSONB로 저장할 내용 (딕셔너리)
    
    Returns:
        생성된 run_memory 정보 딕셔너리
    
    Raises:
        Exception: 생성 실패 시
    """
    supabase = get_client()
    memory_data = {
        "run_id": str(run_id),
        "content": content
    }
    
    result = supabase.table("run_memory").insert(memory_data).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    raise Exception("run_memory 생성 실패: 데이터가 반환되지 않았습니다.")


def update_run_memory(run_id: UUID, content: Dict) -> Dict:
    """
    run_memory 업데이트
    
    Args:
        run_id: 탐색 세션 ID
        content: 업데이트할 JSONB 내용 (딕셔너리)
    
    Returns:
        업데이트된 run_memory 정보 딕셔너리
    
    Raises:
        Exception: 업데이트 실패 시
    """
    supabase = get_client()
    result = supabase.table("run_memory").update({
        "content": content
    }).eq("run_id", str(run_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    raise Exception("run_memory 업데이트 실패: 데이터가 반환되지 않았습니다.")


# ============================================
# Pending Actions 관련 메서드
# ============================================

def create_pending_action(
    run_id: UUID,
    from_node_id: UUID,
    action_type: str,
    action_target: str,
    action_value: str = "",
    status: str = "pending"
) -> Dict:
    """
    pending_action 생성
    
    Args:
        run_id: 탐색 세션 ID
        from_node_id: 시작 노드 ID
        action_type: 액션 타입 ('click', 'fill', 'navigate', 'scroll', 'keyboard', 'wait', 'hover')
        action_target: 액션 대상
        action_value: 액션 값 (기본값: '')
        status: 상태 (기본값: 'pending')
    
    Returns:
        생성된 pending_action 정보 딕셔너리
    
    Raises:
        Exception: 생성 실패 시
    """
    supabase = get_client()
    pending_data = {
        "run_id": str(run_id),
        "from_node_id": str(from_node_id),
        "action_type": action_type,
        "action_target": action_target,
        "action_value": action_value or "",
        "status": status
    }
    
    result = supabase.table("pending_actions").insert(pending_data).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    raise Exception("pending_action 생성 실패: 데이터가 반환되지 않았습니다.")


def delete_pending_action(pending_action_id: UUID) -> bool:
    """
    pending_action 삭제
    
    Args:
        pending_action_id: 삭제할 pending_action ID
    
    Returns:
        삭제 성공 여부
    """
    supabase = get_client()
    result = supabase.table("pending_actions").delete().eq("id", str(pending_action_id)).execute()
    
    # Supabase delete는 삭제된 행 수를 반환하지 않으므로, 에러가 없으면 성공으로 간주
    return True


def get_pending_actions_by_run_id(run_id: UUID, status: Optional[str] = None) -> List[Dict]:
    """
    run_id 기준으로 pending_actions 조회
    
    Args:
        run_id: 탐색 세션 ID
        status: 필터링할 상태 (None이면 모든 상태)
    
    Returns:
        pending_action 리스트
    """
    supabase = get_client()
    query = supabase.table("pending_actions").select("*").eq("run_id", str(run_id))
    
    if status:
        query = query.eq("status", status)
    
    result = query.execute()
    return result.data or []


def get_pending_actions_by_run_and_node(
    run_id: UUID,
    from_node_id: UUID,
    status: Optional[str] = None
) -> List[Dict]:
    """
    run_id와 from_node_id 기준으로 pending_actions 조회
    
    Args:
        run_id: 탐색 세션 ID
        from_node_id: 시작 노드 ID
        status: 필터링할 상태 (None이면 모든 상태)
    
    Returns:
        pending_action 리스트
    """
    supabase = get_client()
    query = supabase.table("pending_actions").select("*").eq("run_id", str(run_id)).eq(
        "from_node_id", str(from_node_id)
    )
    
    if status:
        query = query.eq("status", status)
    
    result = query.execute()
    return result.data or []


def list_pending_actions(
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
    supabase = get_client()
    query = supabase.table("pending_actions").select("*").eq("run_id", str(run_id))
    
    if from_node_id:
        query = query.eq("from_node_id", str(from_node_id))
    
    if status:
        query = query.eq("status", status)
    
    result = query.execute()
    return result.data or []
