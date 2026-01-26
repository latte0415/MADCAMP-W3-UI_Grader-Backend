"""Node Repository
nodes 테이블 관련 데이터 접근 로직
"""
from typing import Dict, List, Optional
from uuid import UUID

from infra.supabase import get_client


def find_node_by_conditions(
    run_id: UUID,
    url_normalized: str,
    a11y_hash: str,
    state_hash: str
) -> Optional[Dict]:
    """
    조건에 맞는 노드 조회
    
    Args:
        run_id: 탐색 세션 ID
        url_normalized: 정규화된 URL
        a11y_hash: 접근성 해시
        state_hash: 상태 해시
    
    Returns:
        노드 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("nodes").select("*").eq("run_id", str(run_id)).eq(
        "url_normalized", url_normalized
    ).eq("a11y_hash", a11y_hash).eq("state_hash", state_hash).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def create_node(node_data: Dict) -> Dict:
    """
    노드 생성
    
    Args:
        node_data: 노드 데이터 딕셔너리
    
    Returns:
        생성된 노드 정보 딕셔너리
    
    Raises:
        Exception: 생성 실패 시
    """
    supabase = get_client()
    result = supabase.table("nodes").insert(node_data).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    raise Exception("노드 생성 실패: 데이터가 반환되지 않았습니다.")


def update_node(node_id: UUID, update_data: Dict) -> Dict:
    """
    노드 업데이트
    
    Args:
        node_id: 노드 ID
        update_data: 업데이트할 데이터 딕셔너리
    
    Returns:
        업데이트된 노드 정보 딕셔너리
    
    Raises:
        Exception: 업데이트 실패 시
    """
    supabase = get_client()
    result = supabase.table("nodes").update(update_data).eq("id", str(node_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    raise Exception("노드 업데이트 실패: 데이터가 반환되지 않았습니다.")


def get_node_by_id(node_id: UUID) -> Optional[Dict]:
    """
    노드 ID로 노드 조회
    
    Args:
        node_id: 노드 ID
    
    Returns:
        노드 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("nodes").select("*").eq("id", str(node_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def update_node_depths(node_id: UUID, depths: Dict[str, int]) -> Dict:
    """
    노드 depth 필드 업데이트
    
    Args:
        node_id: 노드 ID
        depths: depth 딕셔너리 (route_depth, modal_depth, interaction_depth)
    
    Returns:
        업데이트된 노드 정보 딕셔너리
    
    Raises:
        Exception: 업데이트 실패 시
    """
    update_data = {
        "route_depth": depths.get("route_depth"),
        "modal_depth": depths.get("modal_depth"),
        "interaction_depth": depths.get("interaction_depth")
    }
    return update_node(node_id, update_data)
