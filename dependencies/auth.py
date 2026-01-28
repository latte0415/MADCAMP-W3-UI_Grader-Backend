"""인증 관련 의존성"""
from typing import Optional
from fastapi import HTTPException, Header
import base64
import json

from utils.logger import get_logger

logger = get_logger(__name__)


async def get_current_user_id(
    authorization: Optional[str] = Header(None)
) -> str:
    """
    Authorization 헤더에서 Supabase JWT 토큰을 추출하고 user_id를 반환합니다.
    
    Args:
        authorization: Authorization 헤더 값 (Bearer {token} 형식)
    
    Returns:
        user_id (UUID 문자열)
    
    Raises:
        HTTPException: 인증 토큰이 없거나 유효하지 않은 경우
    
    Note:
        JWT 토큰의 payload를 디코딩하여 user_id를 추출합니다.
        프로덕션 환경에서는 토큰 서명 검증을 추가로 수행해야 합니다.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="인증 토큰이 필요합니다. Authorization 헤더에 Bearer 토큰을 포함해주세요."
        )
    
    token = authorization.replace("Bearer ", "").strip()
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="인증 토큰이 유효하지 않습니다."
        )
    
    try:
        # JWT 토큰은 base64로 인코�된 3개의 부분으로 구성됩니다: header.payload.signature
        parts = token.split(".")
        
        if len(parts) != 3:
            raise HTTPException(
                status_code=401,
                detail="토큰 형식이 유효하지 않습니다."
            )
        
        # payload 부분 디코딩
        payload_part = parts[1]
        
        # base64 패딩 추가 (필요한 경우)
        padding = 4 - len(payload_part) % 4
        if padding != 4:
            payload_part += "=" * padding
        
        # base64 디코딩
        decoded_bytes = base64.urlsafe_b64decode(payload_part)
        payload = json.loads(decoded_bytes)
        
        # user_id 추출 (Supabase JWT의 경우 'sub' 필드에 user_id가 있음)
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="토큰에서 사용자 ID를 찾을 수 없습니다."
            )
        
        return user_id
            
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"토큰 디코딩 실패: {e}")
        raise HTTPException(
            status_code=401,
            detail="토큰 형식이 유효하지 않습니다."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"인증 처리 중 오류 발생: {e}", exc_info=True)
        raise HTTPException(
            status_code=401,
            detail="인증 처리 중 오류가 발생했습니다."
        )
