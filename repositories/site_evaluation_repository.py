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
