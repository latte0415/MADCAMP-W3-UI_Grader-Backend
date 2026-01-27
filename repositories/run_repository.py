"""Run Repository
runs 테이블 관련 데이터 접근 로직
"""
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from datetime import datetime

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


def get_runs_by_user_id(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    order_by: str = "created_at",
    order: str = "desc"
) -> Tuple[List[Dict], int]:
    """
    user_id로 runs 리스트 조회 (site_evaluations와 조인)
    
    Args:
        user_id: 사용자 ID
        limit: 반환할 항목 수
        offset: 페이지네이션 오프셋
        status: 상태 필터 (running | completed | failed | stopped, 선택)
        order_by: 정렬 기준 (기본값: created_at)
        order: 정렬 방향 (asc | desc, 기본값: desc)
    
    Returns:
        (runs 리스트, 전체 개수) 튜플
    """
    supabase = get_client()
    
    # 기본 쿼리: user_id 컬럼으로 필터링 (metadata->>user_id 대신 직접 컬럼 사용)
    query = supabase.table("runs").select(
        "id, status, target_url, start_url, created_at, completed_at, metadata"
    ).eq("user_id", user_id)
    
    # status 필터 적용
    if status:
        query = query.eq("status", status)
    
    # 정렬
    if order.lower() == "asc":
        query = query.order(order_by, desc=False)
    else:
        query = query.order(order_by, desc=True)
    
    # 전체 개수 조회
    try:
        count_query = supabase.table("runs").select(
            "id", count="exact"
        ).eq("user_id", user_id)
        if status:
            count_query = count_query.eq("status", status)
        count_result = count_query.execute()
        total = getattr(count_result, 'count', None)
        if total is None:
            total = len(count_result.data or [])
    except Exception as e:
        logger.warning(f"전체 개수 조회 실패, 데이터 길이로 대체: {e}")
        total = 0
    
    # 페이지네이션 적용
    query = query.range(offset, offset + limit - 1)
    
    result = query.execute()
    runs = result.data or []
    
    # 각 run에 대해 site_evaluation 조회 및 포맷팅
    formatted_runs = []
    for run in runs:
        run_id = run.get("id")
        
        # execution_time 계산
        execution_time = None
        created_at = run.get("created_at")
        completed_at = run.get("completed_at")
        
        if created_at and completed_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                execution_time = int((completed_dt - created_dt).total_seconds())
            except Exception as e:
                logger.warning(f"execution_time 계산 실패 (run_id: {run_id}): {e}")
        
        # site_evaluation 조회 (status가 completed인 경우만)
        evaluation = None
        if run.get("status") == "completed":
            try:
                eval_result = supabase.table("site_evaluations").select(
                    "id, total_score, learnability_score, efficiency_score, control_score, created_at"
                ).eq("run_id", run_id).execute()
                
                if eval_result.data and len(eval_result.data) > 0:
                    eval_data = eval_result.data[0]
                    evaluation = {
                        "id": eval_data.get("id"),
                        "total_score": eval_data.get("total_score"),
                        "learnability_score": eval_data.get("learnability_score"),
                        "efficiency_score": eval_data.get("efficiency_score"),
                        "control_score": eval_data.get("control_score"),
                        "created_at": eval_data.get("created_at")
                    }
            except Exception as e:
                logger.warning(f"site_evaluation 조회 실패 (run_id: {run_id}): {e}")
        
        formatted_run = {
            "run_id": run_id,
            "status": run.get("status"),
            "target_url": run.get("target_url"),
            "start_url": run.get("start_url"),
            "created_at": created_at,
            "completed_at": completed_at,
            "execution_time": execution_time,
            "evaluation": evaluation
        }
        formatted_runs.append(formatted_run)
    
    return formatted_runs, total
