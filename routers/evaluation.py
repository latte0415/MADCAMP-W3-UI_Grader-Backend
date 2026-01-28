"""사이트 평가 API 라우터"""
from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field, HttpUrl
from playwright.async_api import async_playwright

from repositories.run_repository import create_run, get_run_by_id
from repositories.site_evaluation_repository import (
    create_site_evaluation,
    create_node_evaluation,
    create_edge_evaluation,
    create_workflow_evaluation,
    get_evaluations_by_user_id
)
from services.site_evaluation_service import SiteEvaluationService
from services.graph_builder_service import start_graph_building
from services.analysis_service import AnalysisService
from dependencies.auth import get_current_user_id
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


class AnalyzeRequest(BaseModel):
    """분석 요청 모델"""
    url: str = Field(..., description="분석할 대상 URL")
    start_url: Optional[str] = Field(None, description="시작 URL (기본값: url과 동일)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="추가 메타데이터")


class FullAnalysisRequest(BaseModel):
    """전체 분석 요청 모델"""
    url: str = Field(..., description="분석할 대상 URL")
    user_id: str = Field(..., description="사용자 ID")


@router.get("/list")
async def get_evaluations(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(50, description="반환할 항목 수", ge=1, le=100),
    offset: int = Query(0, description="페이지네이션 오프셋", ge=0),
    order_by: str = Query("created_at", description="정렬 기준"),
    order: str = Query("desc", description="정렬 방향 (asc | desc)")
) -> Dict[str, Any]:
    """
    사용자별 평가 리스트를 조회합니다.
    
    Args:
        user_id: 인증된 사용자 ID (자동 추출)
        limit: 반환할 항목 수 (기본값: 50)
        offset: 페이지네이션 오프셋 (기본값: 0)
        order_by: 정렬 기준 (기본값: created_at)
        order: 정렬 방향 (asc | desc, 기본값: desc)
    
    Returns:
        평가 리스트 및 페이지네이션 정보
    """
    try:
        # order_by 검증
        allowed_order_by = ["created_at", "timestamp", "total_score", "learnability_score", "efficiency_score", "control_score"]
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
        
        # 평가 리스트 조회
        evaluations, total = get_evaluations_by_user_id(
            user_id=user_id,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order=order.lower()
        )
        
        return {
            "evaluations": evaluations,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"평가 리스트 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"평가 리스트 조회 중 오류가 발생했습니다: {str(e)}"
        )


@router.get("/validate")
async def validate_url(url: str = Query(..., description="검증할 URL")) -> Dict[str, Any]:
    """
    특정 URL이 분석 가능한지(유효한지) 확인합니다.
    
    Args:
        url: 검증할 URL
    
    Returns:
        유효성 검사 결과
    """
    playwright = None
    browser = None
    
    try:
        # URL 형식 검증
        if not url.startswith(("http://", "https://")):
            return {
                "valid": False,
                "url": url,
                "message": "URL은 http:// 또는 https://로 시작해야 합니다.",
                "details": {
                    "accessible": False,
                    "status_code": None,
                    "error": "Invalid URL format"
                }
            }
        
        # Playwright로 접근 가능 여부 확인
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        # 타임아웃 설정 (10초)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
        
        if response:
            status_code = response.status
            accessible = 200 <= status_code < 400
            
            return {
                "valid": accessible,
                "url": url,
                "message": "URL이 분석 가능합니다." if accessible else f"URL에 접근할 수 없습니다 (상태 코드: {status_code})",
                "details": {
                    "accessible": accessible,
                    "status_code": status_code,
                    "error": None if accessible else f"HTTP {status_code}"
                }
            }
        else:
            return {
                "valid": False,
                "url": url,
                "message": "URL에 접근할 수 없습니다.",
                "details": {
                    "accessible": False,
                    "status_code": None,
                    "error": "No response received"
                }
            }
    
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"URL 유효성 검사 실패: {url}, 에러: {error_msg}", exc_info=True)
        
        return {
            "valid": False,
            "url": url,
            "message": f"URL에 접근할 수 없습니다: {error_msg}",
            "details": {
                "accessible": False,
                "status_code": None,
                "error": error_msg
            }
        }
    
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


@router.post("/analyze")
async def analyze_url(
    request: AnalyzeRequest,
    user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    특정 URL에 대한 사이트 평가 분석을 시작합니다.
    
    Args:
        request: 분석 요청 데이터
        user_id: 인증된 사용자 ID (자동 추출)
    
    Returns:
        분석 시작 정보 (run_id 포함)
    """
    try:
        # URL 검증
        if not request.url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail="URL은 http:// 또는 https://로 시작해야 합니다."
            )
        
        # start_url이 없으면 url과 동일하게 설정
        start_url = request.start_url or request.url
        
        # Run 생성 (user_id를 직접 컬럼에 저장)
        metadata = request.metadata or {}
        metadata["user_id"] = user_id  # 하위 호환성을 위해 metadata에도 저장
        
        run_data = {
            "target_url": request.url,
            "start_url": start_url,
            "status": "running",
            "user_id": user_id,  # 직접 컬럼에 저장
            "metadata": metadata
        }
        
        run = create_run(run_data)
        run_id = UUID(run["id"])
        
        # 그래프 구축 시작 (비동기)
        try:
            await start_graph_building(run_id, start_url)
        except Exception as e:
            logger.error(f"그래프 구축 시작 실패: {e}", exc_info=True)
            # Run 상태를 failed로 업데이트
            from repositories.run_repository import update_run
            update_run(run_id, {"status": "failed"})
            raise HTTPException(
                status_code=500,
                detail=f"분석 시작 중 오류가 발생했습니다: {str(e)}"
            )
        
        return {
            "run_id": str(run_id),
            "status": "running",
            "target_url": request.url,
            "start_url": start_url,
            "created_at": run.get("created_at"),
            "message": "분석이 시작되었습니다."
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"분석 시작 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"분석 시작 중 오류가 발생했습니다: {str(e)}"
        )


@router.get("/{run_id}")
async def get_evaluation(
    run_id: UUID,
    include_details: bool = Query(True, description="상세 정보 포함 여부")
) -> Dict[str, Any]:
    """
    특정 run_id의 사이트 평가 결과를 조회합니다.
    
    Args:
        run_id: 평가 실행 ID
        include_details: 상세 정보 포함 여부
    
    Returns:
        평가 결과
    """
    try:
        # Run 존재 확인
        run = get_run_by_id(run_id)
        if not run:
            raise HTTPException(
                status_code=404,
                detail=f"Run을 찾을 수 없습니다: {run_id}"
            )
        
        # 평가 결과 조회
        evaluation_service = SiteEvaluationService()
        evaluation = evaluation_service.get_evaluation_by_run_id(run_id, include_details=include_details)
        
        if not evaluation:
            raise HTTPException(
                status_code=404,
                detail=f"평가 결과를 찾을 수 없습니다. 분석이 아직 완료되지 않았거나 평가 결과가 저장되지 않았습니다."
            )
        
        return evaluation
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"평가 결과 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"평가 결과 조회 중 오류가 발생했습니다: {str(e)}"
        )


def _save_analysis_results_to_db(run_id: UUID, analysis_result: Dict[str, Any]):
    """
    분석 결과를 DB에 저장하는 헬퍼 함수
    
    Args:
        run_id: Run ID
        analysis_result: run_full_analysis의 반환 결과
    """
    try:
        # 0. runs 테이블에 evaluation_result_json 저장
        from repositories.run_repository import update_run
        update_run(run_id, {"evaluation_result_json": analysis_result})
        logger.info(f"runs 테이블에 evaluation_result_json 저장 완료: run_id={run_id}")
        
        # 1. site_evaluation 생성
        site_eval_data = {
            "run_id": str(run_id),
            "timestamp": analysis_result.get("timestamp"),
            "total_score": float(analysis_result.get("total_score", 0)),
            "learnability_score": float(analysis_result.get("category_scores", {}).get("learnability", 0)),
            "efficiency_score": float(analysis_result.get("category_scores", {}).get("efficiency", 0)),
            "control_score": float(analysis_result.get("category_scores", {}).get("control", 0)),
            "node_count": analysis_result.get("summary", {}).get("node_count", 0),
            "edge_count": analysis_result.get("summary", {}).get("edge_count", 0),
            "path_count": analysis_result.get("summary", {}).get("path_count", 0),
        }
        site_evaluation = create_site_evaluation(site_eval_data)
        site_evaluation_id = UUID(site_evaluation["id"])
        
        # 2. node_evaluations 생성
        static_analysis = analysis_result.get("details", {}).get("static_analysis", [])
        for node_result in static_analysis:
            node_result_data = node_result.get("result", {})
            learnability = node_result_data.get("learnability", {})
            control = node_result_data.get("control", {})
            
            node_eval_data = {
                "site_evaluation_id": str(site_evaluation_id),
                "node_id": str(node_result.get("node_id")),
                "url": node_result.get("url", ""),
                "learnability_score": float(learnability.get("score", 0)),
                "efficiency_score": 0.0,  # static analysis에는 efficiency가 없음
                "control_score": float(control.get("score", 0)),
                "learnability_items": learnability.get("items", []),
                "efficiency_items": [],
                "control_items": control.get("items", []),
            }
            create_node_evaluation(node_eval_data)
        
        # 3. edge_evaluations 생성
        transition_analysis = analysis_result.get("details", {}).get("transition_analysis", [])
        for edge_result in transition_analysis:
            edge_result_data = edge_result.get("result", {})
            efficiency = edge_result_data.get("efficiency", {})
            control = edge_result_data.get("control", {})
            
            # latency 정보 추출
            latency_info = efficiency.get("latency", {})
            
            edge_eval_data = {
                "site_evaluation_id": str(site_evaluation_id),
                "edge_id": str(edge_result.get("edge_id")),
                "action": edge_result.get("action", ""),
                "learnability_score": 0.0,  # transition analysis에는 learnability가 없음
                "efficiency_score": float(efficiency.get("score", 0)),
                "control_score": float(control.get("score", 0)),
                "latency_duration_ms": latency_info.get("duration_ms"),
                "latency_status": latency_info.get("status"),
                "latency_description": latency_info.get("description"),
                "learnability_passed": [],
                "learnability_failed": [],
                "efficiency_passed": efficiency.get("passed", []),
                "efficiency_failed": efficiency.get("failed", []),
                "control_passed": control.get("passed", []),
                "control_failed": control.get("failed", []),
            }
            create_edge_evaluation(edge_eval_data)
        
        # 4. workflow_evaluations 생성
        workflow_analysis = analysis_result.get("details", {}).get("workflow_analysis", [])
        for workflow_result in workflow_analysis:
            workflow_eval_data = {
                "site_evaluation_id": str(site_evaluation_id),
                "workflow_data": workflow_result,
            }
            create_workflow_evaluation(workflow_eval_data)
        
        logger.info(f"분석 결과가 DB에 저장되었습니다. run_id: {run_id}, site_evaluation_id: {site_evaluation_id}")
        
    except Exception as e:
        logger.error(f"분석 결과 DB 저장 실패 (run_id: {run_id}): {e}", exc_info=True)
        raise


@router.post("/full-analysis")
async def run_full_analysis_api(request: FullAnalysisRequest) -> Dict[str, Any]:
    """
    전체 분석을 실행하고 결과를 DB에 저장합니다.
    
    Args:
        request: 전체 분석 요청 데이터 (url, user_id)
    
    Returns:
        run_id
    """
    try:
        # URL 검증
        if not request.url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail="URL은 http:// 또는 https://로 시작해야 합니다."
            )
        
        # Run 생성 (user_id를 직접 컬럼에 저장)
        run_data = {
            "target_url": request.url,
            "start_url": request.url,
            "status": "running",
            "user_id": request.user_id,  # 직접 컬럼에 저장
            "metadata": {
                "user_id": request.user_id,  # 하위 호환성을 위해 metadata에도 저장
                "analysis_type": "full_analysis"
            }
        }
        
        run = create_run(run_data)
        run_id = UUID(run["id"])
        
        logger.info(f"전체 분석 시작: run_id={run_id}, url={request.url}, user_id={request.user_id}")
        
        # 전체 분석 실행 (동기적으로 실행 - 시간이 오래 걸릴 수 있음)
        try:
            analysis_result = AnalysisService.run_full_analysis(run_id)
            
            # 결과를 DB에 저장
            _save_analysis_results_to_db(run_id, analysis_result)
            
            # Run 상태를 completed로 업데이트
            from repositories.run_repository import update_run
            update_run(run_id, {"status": "completed"})
            
            logger.info(f"전체 분석 완료: run_id={run_id}")
            
        except Exception as e:
            logger.error(f"전체 분석 실행 실패: {e}", exc_info=True)
            # Run 상태를 failed로 업데이트
            from repositories.run_repository import update_run
            update_run(run_id, {"status": "failed"})
            raise HTTPException(
                status_code=500,
                detail=f"분석 실행 중 오류가 발생했습니다: {str(e)}"
            )
        
        return {
            "run_id": str(run_id),
            "message": "전체 분석이 완료되었습니다."
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"전체 분석 API 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"전체 분석 요청 처리 중 오류가 발생했습니다: {str(e)}"
        )
