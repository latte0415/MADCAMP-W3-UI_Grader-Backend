"""Node Repository
nodes 테이블 관련 데이터 접근 로직
"""
from typing import Dict, List, Optional
from uuid import UUID

from infra.supabase import get_client
from exceptions.repository import EntityCreationError, EntityUpdateError, DatabaseConnectionError
from utils.logger import get_logger

logger = get_logger(__name__)


def find_node_by_conditions(
    run_id: UUID,
    url_normalized: str,
    a11y_hash: str,
    state_hash: str,
    input_state_hash: str
) -> Optional[Dict]:
    """
    조건에 맞는 노드 조회
    
    Args:
        run_id: 탐색 세션 ID
        url_normalized: 정규화된 URL
        a11y_hash: 접근성 해시
        state_hash: 상태 해시
        input_state_hash: 입력 상태 해시
    
    Returns:
        노드 정보 딕셔너리 또는 None
    
    Note:
        같은 입력 상태(input_state_hash)를 가진 노드를 우선적으로 찾습니다.
        입력 상태가 같으면 a11y_hash 차이는 무시합니다.
    """
    supabase = get_client()
    
    # 1. 모든 조건이 일치하는 노드 찾기 (기존 로직)
    result = supabase.table("nodes").select("*").eq("run_id", str(run_id)).eq(
        "url_normalized", url_normalized
    ).eq("a11y_hash", a11y_hash).eq("state_hash", state_hash).eq("input_state_hash", input_state_hash).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    
    # 2. 입력 상태가 같으면 같은 노드로 인식 (a11y_hash는 무시)
    # 같은 입력 상태면 같은 노드로 봐야 함 (같은 값 입력 시 같은 노드)
    if input_state_hash:
        result = supabase.table("nodes").select("*").eq("run_id", str(run_id)).eq(
            "url_normalized", url_normalized
        ).eq("state_hash", state_hash).eq("input_state_hash", input_state_hash).execute()
        
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
        EntityCreationError: 생성 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("nodes").insert(node_data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityCreationError("노드", reason="데이터가 반환되지 않았습니다.")
    except EntityCreationError:
        raise
    except Exception as e:
        logger.error(f"노드 생성 중 예외 발생: {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityCreationError("노드", original_error=e)


def update_node(node_id: UUID, update_data: Dict) -> Dict:
    """
    노드 업데이트
    
    Args:
        node_id: 노드 ID
        update_data: 업데이트할 데이터 딕셔너리
    
    Returns:
        업데이트된 노드 정보 딕셔너리
    
    Raises:
        EntityUpdateError: 업데이트 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("nodes").update(update_data).eq("id", str(node_id)).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityUpdateError("노드", entity_id=str(node_id), reason="데이터가 반환되지 않았습니다.")
    except EntityUpdateError:
        raise
    except Exception as e:
        logger.error(f"노드 업데이트 중 예외 발생 (node_id: {node_id}): {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityUpdateError("노드", entity_id=str(node_id), original_error=e)


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


def get_nodes_by_run_id(run_id: UUID) -> List[Dict]:
    """
    run_id로 노드 목록 조회
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        노드 리스트
    """
    supabase = get_client()
    result = supabase.table("nodes").select("*").eq("run_id", str(run_id)).order("created_at").execute()
    return result.data or []


def find_equivalent_nodes(
    run_id: UUID,
    state_hash: str,
    a11y_hash: str,
    input_state_hash: str,
    exclude_node_id: Optional[UUID] = None
) -> List[Dict]:
    """
    동치 노드 조회 (같은 state_hash, a11y_hash, input_state_hash를 가진 노드)
    
    Args:
        run_id: 탐색 세션 ID
        state_hash: 상태 해시
        a11y_hash: 접근성 해시
        input_state_hash: 입력 상태 해시
        exclude_node_id: 제외할 노드 ID (선택적)
    
    Returns:
        동치 노드 리스트
    """
    supabase = get_client()
    query = supabase.table("nodes").select("*").eq("run_id", str(run_id)).eq(
        "state_hash", state_hash
    ).eq("a11y_hash", a11y_hash).eq("input_state_hash", input_state_hash)
    
    if exclude_node_id:
        query = query.neq("id", str(exclude_node_id))
    
    result = query.execute()
    return result.data or []
