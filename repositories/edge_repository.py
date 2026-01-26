"""Edge Repository
edges 테이블 관련 데이터 접근 로직
"""
from typing import Dict, Optional
from uuid import UUID

from infra.supabase import get_client


def find_duplicate_edge(
    run_id: UUID,
    from_node_id: UUID,
    action_type: str,
    action_target: str,
    action_value: str = ""
) -> Optional[Dict]:
    """
    중복 엣지 조회
    
    Args:
        run_id: 탐색 세션 ID
        from_node_id: 시작 노드 ID
        action_type: 액션 타입
        action_target: 액션 대상
        action_value: 액션 값
    
    Returns:
        기존 엣지 데이터 또는 None
    """
    supabase = get_client()
    result = supabase.table("edges").select("*").eq("run_id", str(run_id)).eq(
        "from_node_id", str(from_node_id)
    ).eq("action_type", action_type).eq(
        "action_target", action_target
    ).eq("action_value", action_value).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def create_edge(edge_data: Dict) -> Dict:
    """
    엣지 생성
    
    Args:
        edge_data: 엣지 데이터 딕셔너리
    
    Returns:
        생성된 엣지 정보 딕셔너리
    
    Raises:
        Exception: 생성 실패 시
    """
    supabase = get_client()
    result = supabase.table("edges").insert(edge_data).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    raise Exception("엣지 생성 실패: 데이터가 반환되지 않았습니다.")
