"""Run Repository
runs 테이블 관련 데이터 접근 로직
"""
from typing import Dict, List, Optional
from uuid import UUID

from infra.supabase import get_client
from exceptions.repository import EntityCreationError, EntityUpdateError, DatabaseConnectionError
from utils.logger import get_logger

logger = get_logger(__name__)


def get_run_by_id(run_id: UUID) -> Optional[Dict]:
    """
    run_id로 run 조회
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        run 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("runs").select("*").eq("id", str(run_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def create_run(run_data: Dict) -> Dict:
    """
    run 생성
    
    Args:
        run_data: run 데이터 딕셔너리
    
    Returns:
        생성된 run 정보 딕셔너리
    
    Raises:
        EntityCreationError: 생성 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("runs").insert(run_data).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityCreationError("run", reason="데이터가 반환되지 않았습니다.")
    except EntityCreationError:
        raise
    except Exception as e:
        logger.error(f"run 생성 중 예외 발생: {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityCreationError("run", original_error=e)


def update_run(run_id: UUID, update_data: Dict) -> Dict:
    """
    run 업데이트
    
    Args:
        run_id: run ID
        update_data: 업데이트할 데이터 딕셔너리
    
    Returns:
        업데이트된 run 정보 딕셔너리
    
    Raises:
        EntityUpdateError: 업데이트 실패 시
        DatabaseConnectionError: 데이터베이스 연결 실패 시
    """
    try:
        supabase = get_client()
        result = supabase.table("runs").update(update_data).eq("id", str(run_id)).execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise EntityUpdateError("run", entity_id=str(run_id), reason="데이터가 반환되지 않았습니다.")
    except EntityUpdateError:
        raise
    except Exception as e:
        logger.error(f"run 업데이트 중 예외 발생 (run_id: {run_id}): {e}", exc_info=True)
        if "connection" in str(e).lower() or "network" in str(e).lower():
            raise DatabaseConnectionError(original_error=e)
        raise EntityUpdateError("run", entity_id=str(run_id), original_error=e)


def get_runs_by_status(status: str) -> List[Dict]:
    """
    status로 run 목록 조회
    
    Args:
        status: run 상태 (running, completed, failed, stopped)
    
    Returns:
        run 리스트
    """
    supabase = get_client()
    result = supabase.table("runs").select("*").eq("status", status).order("created_at", desc=True).execute()
    return result.data or []
