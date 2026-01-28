"""노드 API 라우터"""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Response

from repositories.node_repository import get_node_by_id
from infra.supabase import download_storage_file
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("/{node_id}/screenshot")
async def get_node_screenshot(node_id: UUID):
    """
    특정 노드의 스크린샷 이미지를 반환합니다.
    
    Args:
        node_id: 노드 ID
    
    Returns:
        이미지 바이너리 (image/png)
    """
    try:
        # 1. 노드 조회
        node = get_node_by_id(node_id)
        if not node:
            raise HTTPException(
                status_code=404,
                detail=f"노드를 찾을 수 없습니다: {node_id}"
            )
        
        screenshot_ref = node.get("screenshot_ref")
        if not screenshot_ref:
            raise HTTPException(
                status_code=404,
                detail=f"노드에 스크린샷이 없습니다: {node_id}"
            )
        
        # 2. 스토리지에서 이미지 다운로드
        try:
            screenshot_bytes = download_storage_file(screenshot_ref)
        except Exception as e:
            logger.error(f"스크린샷 다운로드 실패: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="스크린샷 파일을 가져오는 데 실패했습니다."
            )
        
        # 3. 이미지 반환
        return Response(content=screenshot_bytes, media_type="image/png")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스크린샷 조회 API 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"스크린샷 조회 중 오류가 발생했습니다: {str(e)}"
        )
