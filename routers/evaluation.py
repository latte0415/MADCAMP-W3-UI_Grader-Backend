"""사이트 평가 API 라우터"""
from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from playwright.async_api import async_playwright

from repositories.run_repository import create_run, get_run_by_id
from services.site_evaluation_service import SiteEvaluationService
from services.graph_builder_service import start_graph_building
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


class AnalyzeRequest(BaseModel):
    """분석 요청 모델"""
    url: str = Field(..., description="분석할 대상 URL")
    start_url: Optional[str] = Field(None, description="시작 URL (기본값: url과 동일)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="추가 메타데이터")


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
async def analyze_url(request: AnalyzeRequest) -> Dict[str, Any]:
    """
    특정 URL에 대한 사이트 평가 분석을 시작합니다.
    
    Args:
        request: 분석 요청 데이터
    
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
        
        # Run 생성
        run_data = {
            "target_url": request.url,
            "start_url": start_url,
            "status": "running",
            "metadata": request.metadata or {}
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
