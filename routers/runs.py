"""Runs API 라우터"""
from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Depends

from repositories.run_repository import get_runs_by_user_id, get_run_by_id
from dependencies.auth import get_current_user_id
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("")
async def get_runs(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(50, description="반환할 항목 수", ge=1, le=100),
    offset: int = Query(0, description="페이지네이션 오프셋", ge=0),
    status: Optional[str] = Query(None, description="상태 필터 (running | completed | failed | stopped)"),
    order_by: str = Query("created_at", description="정렬 기준"),
    order: str = Query("desc", description="정렬 방향 (asc | desc)")
) -> Dict[str, Any]:
    """
    사용자별 평가 요청(runs) 리스트를 조회합니다.
    
    Args:
        user_id: 인증된 사용자 ID (자동 추출)
        limit: 반환할 항목 수 (기본값: 50)
        offset: 페이지네이션 오프셋 (기본값: 0)
        status: 상태 필터 (running | completed | failed | stopped, 선택)
        order_by: 정렬 기준 (기본값: created_at)
        order: 정렬 방향 (asc | desc, 기본값: desc)
    
    Returns:
        runs 리스트 및 페이지네이션 정보
    """
    try:
        # status 검증
        if status and status not in ["running", "completed", "failed", "stopped"]:
            raise HTTPException(
                status_code=400,
                detail="status는 다음 중 하나여야 합니다: running, completed, failed, stopped"
            )
        
        # order_by 검증
        allowed_order_by = ["created_at", "completed_at", "status"]
        if order_by not in allowed_order_by:
            raise HTTPException(
                status_code=400,
                detail=f"order_by는 다음 중 하나여야 합니다: {', '.join(allowed_order_by)}"
            )
        
        # order 검증
        if order.lower() not in ["asc", "desc"]:
            raise HTTPException(
                status_code=400,
                detail="order는 'asc' 또는 'desc'여야 합니다."
            )
        
        # runs 리스트 조회
        runs, total = get_runs_by_user_id(
            user_id=user_id,
            limit=limit,
            offset=offset,
            status=status,
            order_by=order_by,
            order=order.lower()
        )
        
        return {
            "runs": runs,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"runs 리스트 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"runs 리스트 조회 중 오류가 발생했습니다: {str(e)}"
        )


@router.get("/{run_id}/evaluation-result")
async def get_evaluation_result(run_id: UUID) -> Dict[str, Any]:
    """
    특정 run_id의 평가 결과 JSON을 조회합니다.
    
    Args:
        run_id: 평가 실행 ID
    
    Returns:
        evaluation_result_json (평가 완료된 전체 JSON 결과)
    """
    try:
        # Run 존재 확인
        run = get_run_by_id(run_id)
        if not run:
            raise HTTPException(
                status_code=404,
                detail=f"Run을 찾을 수 없습니다: {run_id}"
            )
        
        # evaluation_result_json 조회
        evaluation_result_json = run.get("evaluation_result_json")
        
        if evaluation_result_json is None:
            raise HTTPException(
                status_code=404,
                detail=f"평가 결과를 찾을 수 없습니다. 분석이 아직 완료되지 않았거나 평가 결과가 저장되지 않았습니다."
            )
        
        return {
            "run_id": str(run_id),
            "status": run.get("status"),
            "evaluation_result": evaluation_result_json
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"평가 결과 조회 실패 (run_id: {run_id}): {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"평가 결과 조회 중 오류가 발생했습니다: {str(e)}"
        )
