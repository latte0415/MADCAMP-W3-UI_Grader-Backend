"""Edge Repository
edges 테이블 관련 데이터 접근 로직
"""
from typing import Dict, List, Optional
from uuid import UUID

from infra.supabase import get_client
from exceptions.repository import EntityCreationError, EntityUpdateError, DatabaseConnectionError
from utils.logger import get_logger

logger = get_logger(__name__)


def find_duplicate_edge(
    run_id: UUID,
    from_node_id: UUID,
    action_type: str,
    action_target: str,
    action_value: str = "",
    outcome: Optional[str] = "success"  # 성공한 엣지만 체크 (기본값: "success")
) -> Optional[Dict]:
    """
    중복 엣지 조회
    
    Args:
        run_id: 탐색 세션 ID
        from_node_id: 시작 노드 ID
        action_type: 액션 타입
        action_target: 액션 대상
        action_value: 액션 값
        outcome: 엣지 결과 필터 (기본값: "success" - 성공한 엣지만 체크)
                 None이면 모든 outcome 체크
    
    Returns:
        기존 엣지 데이터 또는 None
    """
    supabase = get_client()
    query = supabase.table("edges").select("*").eq("run_id", str(run_id)).eq(
        "from_node_id", str(from_node_id)
    ).eq("action_type", action_type).eq(
        "action_target", action_target
    ).eq("action_value", action_value)
    
    # outcome 필터 추가 (성공한 엣지만 중복으로 체크)
    if outcome is not None:
        query = query.eq("outcome", outcome)
    
    result = query.execute()
    
    if result.data and len(result.data) > 0:
        # 여러 개의 엣지가 있으면 가장 최근 것(created_at 기준)을 반환
        sorted_data = sorted(result.data, key=lambda x: x.get("created_at", ""), reverse=True)
        return sorted_data[0]
    return None


def count_failed_edges(
    run_id: UUID,
    from_node_id: UUID,
    action_type: str,
    action_target: str,
    action_value: str = ""
) -> int:
    """
    실패한 엣지 개수 조회 (재시도 제한용)
    
    Args:
        run_id: 탐색 세션 ID
        from_node_id: 시작 노드 ID
        action_type: 액션 타입
        action_target: 액션 대상
        action_value: 액션 값
    
    Returns:
        실패한 엣지 개수
    """
    supabase = get_client()
    result = supabase.table("edges").select("id", count="exact").eq("run_id", str(run_id)).eq(
        "from_node_id", str(from_node_id)
    ).eq("action_type", action_type).eq(
        "action_target", action_target
    ).eq("action_value", action_value).eq("outcome", "fail").execute()
    
    return result.count if result.count is not None else 0


def find_edge_by_nodes(
    run_id: UUID,
    from_node_id: UUID,
    to_node_id: UUID
) -> Optional[Dict]:
    """
    같은 노드 간 엣지 조회
    
    Args:
        run_id: 탐색 세션 ID
        from_node_id: 시작 노드 ID
        to_node_id: 종료 노드 ID
    
    Returns:
        기존 엣지 데이터 또는 None
    """
    supabase = get_client()
    result = supabase.table("edges").select("*").eq("run_id", str(run_id)).eq(
        "from_node_id", str(from_node_id)
    ).eq("to_node_id", str(to_node_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def delete_edge(edge_id: UUID) -> bool:
    """
    엣지 삭제
    
    Args:
        edge_id: 엣지 ID
    
    Returns:
        삭제 성공 여부
    """
    supabase = get_client()
    result = supabase.table("edges").delete().eq("id", str(edge_id)).execute()
    return result.data is not None


def create_edge(edge_data: Dict) -> Dict:
    """
    엣지 생성
    
    Args:
        edge_data: 엣지 데이터 딕셔너리
    
    Returns:
        생성된 엣지 정보 딕셔너리
    
    Raises:
        EntityCreationError: 생성 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("edges").insert(edge_data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityCreationError("엣지", reason="데이터가 반환되지 않았습니다.")
    except EntityCreationError:
        raise
    except Exception as e:
        logger.error(f"엣지 생성 중 예외 발생: {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityCreationError("엣지", original_error=e)


def get_edge_by_id(edge_id: UUID) -> Optional[Dict]:
    """
    엣지 ID로 엣지 조회
    
    Args:
        edge_id: 엣지 ID
    
    Returns:
        엣지 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("edges").select("*").eq("id", str(edge_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def update_edge_intent_label(edge_id: UUID, intent_label: str) -> Dict:
    """
    엣지의 intent_label 필드 업데이트
    
    Args:
        edge_id: 엣지 ID
        intent_label: 의도 라벨 (15자 이내 권장)
    
    Returns:
        업데이트된 엣지 정보 딕셔너리
    
    Raises:
        EntityUpdateError: 업데이트 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("edges").update({"intent_label": intent_label}).eq("id", str(edge_id)).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityUpdateError("엣지", entity_id=str(edge_id), reason="intent_label 업데이트 실패: 데이터가 반환되지 않았습니다.")
    except EntityUpdateError:
        raise
    except Exception as e:
        logger.error(f"엣지 intent_label 업데이트 중 예외 발생 (edge_id: {edge_id}): {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityUpdateError("엣지", entity_id=str(edge_id), original_error=e)


def get_edges_by_run_id(run_id: UUID) -> List[Dict]:
    """
    run_id로 엣지 목록 조회
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        엣지 리스트
    """
    supabase = get_client()
    result = supabase.table("edges").select("*").eq("run_id", str(run_id)).order("created_at").execute()
    return result.data or []


def count_edges_by_run_id(run_id: UUID) -> int:
    """
    run_id로 엣지 개수 조회
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        엣지 개수
    """
    supabase = get_client()
    result = supabase.table("edges").select("id", count="exact").eq("run_id", str(run_id)).execute()
    return result.count if result.count is not None else 0


def count_recent_edges_by_run_id(run_id: UUID, seconds: int) -> int:
    """
    run_id로 최근 N초 동안 생성된 엣지 개수 조회
    
    Args:
        run_id: 탐색 세션 ID
        seconds: 최근 N초
    
    Returns:
        최근 엣지 개수
    """
    from datetime import datetime, timedelta
    
    supabase = get_client()
    threshold_time = datetime.utcnow() - timedelta(seconds=seconds)
    threshold_time_str = threshold_time.isoformat() + "Z"
    
    result = supabase.table("edges").select(
        "id", count="exact"
    ).eq("run_id", str(run_id)).gte("created_at", threshold_time_str).execute()
    
    return result.count if result.count is not None else 0


def count_success_edges_by_run_id(run_id: UUID) -> int:
    """
    run_id로 성공한 엣지 개수 조회
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        성공한 엣지 개수
    """
    supabase = get_client()
    result = supabase.table("edges").select("id", count="exact").eq("run_id", str(run_id)).eq("outcome", "success").execute()
    return result.count if result.count is not None else 0


def count_recent_success_edges_by_run_id(run_id: UUID, seconds: int) -> int:
    """
    run_id로 최근 N초 동안 생성된 성공한 엣지 개수 조회
    
    Args:
        run_id: 탐색 세션 ID
        seconds: 최근 N초
    
    Returns:
        최근 성공한 엣지 개수
    """
    from datetime import datetime, timedelta
    
    supabase = get_client()
    threshold_time = datetime.utcnow() - timedelta(seconds=seconds)
    threshold_time_str = threshold_time.isoformat() + "Z"
    
    result = supabase.table("edges").select(
        "id", count="exact"
    ).eq("run_id", str(run_id)).eq("outcome", "success").gte("created_at", threshold_time_str).execute()
    
    return result.count if result.count is not None else 0
