"""pending_actions 서비스"""
from typing import Dict, List, Optional
from uuid import UUID

from infra.supabase import get_client


def create_pending_action(
    run_id: UUID,
    from_node_id: UUID,
    action: Dict,
    status: str = "pending"
) -> Dict:
    """
    pending_actions에 액션을 저장합니다.
    """
    supabase = get_client()
    action_value = action.get("action_value", "") or ""
    pending_data = {
        "run_id": str(run_id),
        "from_node_id": str(from_node_id),
        "action_type": action["action_type"],
        "action_target": action["action_target"],
        "action_value": action_value,
        "status": status
    }
    result = supabase.table("pending_actions").insert(pending_data).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]
    raise Exception("pending_actions 저장 실패: 데이터가 반환되지 않았습니다.")


def list_pending_actions(
    run_id: UUID,
    from_node_id: Optional[UUID] = None,
    status: Optional[str] = "pending"
) -> List[Dict]:
    """
    pending_actions를 조회합니다.
    """
    supabase = get_client()
    query = supabase.table("pending_actions").select("*").eq("run_id", str(run_id))
    if from_node_id:
        query = query.eq("from_node_id", str(from_node_id))
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return result.data or []
