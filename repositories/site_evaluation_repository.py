"""Site Evaluation Repository
사이트 평가 결과 관련 데이터 접근 로직
"""
from typing import Dict, List, Optional
from uuid import UUID

from infra.supabase import get_client
from exceptions.repository import EntityCreationError, EntityUpdateError, DatabaseConnectionError
from utils.logger import get_logger

logger = get_logger(__name__)


def create_site_evaluation(evaluation_data: Dict) -> Dict:
    """
    사이트 평가 결과 생성
    
    Args:
        evaluation_data: 평가 데이터 딕셔너리
    
    Returns:
        생성된 평가 정보 딕셔너리
    
    Raises:
        EntityCreationError: 생성 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("site_evaluations").insert(evaluation_data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityCreationError("사이트 평가", reason="데이터가 반환되지 않았습니다.")
    except EntityCreationError:
        raise
    except Exception as e:
        logger.error(f"사이트 평가 생성 중 예외 발생: {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityCreationError("사이트 평가", original_error=e)


def get_site_evaluation_by_run_id(run_id: UUID) -> Optional[Dict]:
    """
    run_id로 사이트 평가 결과 조회
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        평가 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("site_evaluations").select("*").eq("run_id", str(run_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def get_site_evaluation_by_id(evaluation_id: UUID) -> Optional[Dict]:
    """
    평가 ID로 사이트 평가 결과 조회
    
    Args:
        evaluation_id: 평가 ID
    
    Returns:
        평가 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("site_evaluations").select("*").eq("id", str(evaluation_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def create_node_evaluation(evaluation_data: Dict) -> Dict:
    """
    노드 평가 결과 생성
    
    Args:
        evaluation_data: 노드 평가 데이터 딕셔너리
    
    Returns:
        생성된 노드 평가 정보 딕셔너리
    
    Raises:
        EntityCreationError: 생성 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("node_evaluations").insert(evaluation_data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityCreationError("노드 평가", reason="데이터가 반환되지 않았습니다.")
    except EntityCreationError:
        raise
    except Exception as e:
        logger.error(f"노드 평가 생성 중 예외 발생: {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityCreationError("노드 평가", original_error=e)


def get_node_evaluations_by_site_evaluation_id(site_evaluation_id: UUID) -> List[Dict]:
    """
    사이트 평가 ID로 노드 평가 목록 조회
    
    Args:
        site_evaluation_id: 사이트 평가 ID
    
    Returns:
        노드 평가 리스트
    """
    supabase = get_client()
    result = supabase.table("node_evaluations").select("*").eq(
        "site_evaluation_id", str(site_evaluation_id)
    ).order("created_at").execute()
    return result.data or []


def get_node_evaluation_by_node_id(site_evaluation_id: UUID, node_id: UUID) -> Optional[Dict]:
    """
    노드 ID로 노드 평가 조회
    
    Args:
        site_evaluation_id: 사이트 평가 ID
        node_id: 노드 ID
    
    Returns:
        노드 평가 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("node_evaluations").select("*").eq(
        "site_evaluation_id", str(site_evaluation_id)
    ).eq("node_id", str(node_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def create_edge_evaluation(evaluation_data: Dict) -> Dict:
    """
    엣지 평가 결과 생성
    
    Args:
        evaluation_data: 엣지 평가 데이터 딕셔너리
    
    Returns:
        생성된 엣지 평가 정보 딕셔너리
    
    Raises:
        EntityCreationError: 생성 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("edge_evaluations").insert(evaluation_data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityCreationError("엣지 평가", reason="데이터가 반환되지 않았습니다.")
    except EntityCreationError:
        raise
    except Exception as e:
        logger.error(f"엣지 평가 생성 중 예외 발생: {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityCreationError("엣지 평가", original_error=e)


def get_edge_evaluations_by_site_evaluation_id(site_evaluation_id: UUID) -> List[Dict]:
    """
    사이트 평가 ID로 엣지 평가 목록 조회
    
    Args:
        site_evaluation_id: 사이트 평가 ID
    
    Returns:
        엣지 평가 리스트
    """
    supabase = get_client()
    result = supabase.table("edge_evaluations").select("*").eq(
        "site_evaluation_id", str(site_evaluation_id)
    ).order("created_at").execute()
    return result.data or []


def get_edge_evaluation_by_edge_id(site_evaluation_id: UUID, edge_id: UUID) -> Optional[Dict]:
    """
    엣지 ID로 엣지 평가 조회
    
    Args:
        site_evaluation_id: 사이트 평가 ID
        edge_id: 엣지 ID
    
    Returns:
        엣지 평가 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("edge_evaluations").select("*").eq(
        "site_evaluation_id", str(site_evaluation_id)
    ).eq("edge_id", str(edge_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def create_workflow_evaluation(evaluation_data: Dict) -> Dict:
    """
    워크플로우 평가 결과 생성
    
    Args:
        evaluation_data: 워크플로우 평가 데이터 딕셔너리
    
    Returns:
        생성된 워크플로우 평가 정보 딕셔너리
    
    Raises:
        EntityCreationError: 생성 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("workflow_evaluations").insert(evaluation_data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityCreationError("워크플로우 평가", reason="데이터가 반환되지 않았습니다.")
    except EntityCreationError:
        raise
    except Exception as e:
        logger.error(f"워크플로우 평가 생성 중 예외 발생: {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityCreationError("워크플로우 평가", original_error=e)


def get_workflow_evaluations_by_site_evaluation_id(site_evaluation_id: UUID) -> List[Dict]:
    """
    사이트 평가 ID로 워크플로우 평가 목록 조회
    
    Args:
        site_evaluation_id: 사이트 평가 ID
    
    Returns:
        워크플로우 평가 리스트
    """
    supabase = get_client()
    result = supabase.table("workflow_evaluations").select("*").eq(
        "site_evaluation_id", str(site_evaluation_id)
    ).order("created_at").execute()
    return result.data or []


def get_evaluations_by_user_id(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    order_by: str = "created_at",
    order: str = "desc"
) -> tuple[List[Dict], int]:
    """
    user_id로 평가 리스트 조회 (runs 테이블과 조인하여 target_url 포함)
    
    Args:
        user_id: 사용자 ID
        limit: 반환할 항목 수
        offset: 페이지네이션 오프셋
        order_by: 정렬 기준 (기본값: created_at)
        order: 정렬 방향 (asc | desc, 기본값: desc)
    
    Returns:
        (평가 리스트, 전체 개수) 튜플
    """
    supabase = get_client()
    
    # 1. 먼저 runs 테이블에서 해당 user_id의 run_id 목록 조회 (user_id 컬럼 사용)
    runs_query = supabase.table("runs").select("id").eq("user_id", user_id)
    runs_result = runs_query.execute()
    run_ids = [run["id"] for run in (runs_result.data or [])]
    
    if not run_ids:
        return [], 0
    
    # 2. site_evaluations 테이블에서 해당 run_id들의 평가 조회 (runs와 조인)
    query = supabase.table("site_evaluations").select(
        "id, run_id, timestamp, total_score, learnability_score, efficiency_score, control_score, created_at, runs(target_url, status)"
    ).in_("run_id", run_ids)
    
    # 정렬
    if order.lower() == "asc":
        query = query.order(order_by, desc=False)
    else:
        query = query.order(order_by, desc=True)
    
    # 전체 개수 조회
    try:
        count_query = supabase.table("site_evaluations").select(
            "id", count="exact"
        ).in_("run_id", run_ids)
        count_result = count_query.execute()
        # Supabase Python 클라이언트는 count 속성을 제공합니다
        total = getattr(count_result, 'count', None)
        if total is None:
            # count 속성이 없는 경우 데이터 길이로 대체
            total = len(count_result.data or [])
    except Exception as e:
        logger.warning(f"전체 개수 조회 실패, 데이터 길이로 대체: {e}")
        # 전체 개수 조회 실패 시 평가 리스트 길이로 대체 (부정확할 수 있음)
        total = 0
    
    # 페이지네이션 적용
    query = query.range(offset, offset + limit - 1)
    
    result = query.execute()
    evaluations = result.data or []
    
    # 응답 형식 변환
    formatted_evaluations = []
    for eval_data in evaluations:
        # runs가 리스트일 수도 있고 딕셔너리일 수도 있음
        run_data = eval_data.get("runs")
        if isinstance(run_data, list) and len(run_data) > 0:
            run_data = run_data[0]
        elif not isinstance(run_data, dict):
            run_data = {}
        
        formatted_eval = {
            "id": eval_data.get("id"),
            "run_id": eval_data.get("run_id"),
            "target_url": run_data.get("target_url", "") if run_data else "",
            "total_score": eval_data.get("total_score"),
            "learnability_score": eval_data.get("learnability_score"),
            "efficiency_score": eval_data.get("efficiency_score"),
            "control_score": eval_data.get("control_score"),
            "created_at": eval_data.get("created_at"),
            "timestamp": eval_data.get("timestamp") or eval_data.get("created_at"),
            "status": run_data.get("status", "completed") if run_data else "completed"
        }
        formatted_evaluations.append(formatted_eval)
    
    return formatted_evaluations, total
