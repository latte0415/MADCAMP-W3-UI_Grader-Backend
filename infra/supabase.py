"""Supabase 클라이언트 초기화"""
import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

from exceptions.repository import DatabaseConnectionError
from utils.logger import get_logger

logger = get_logger(__name__)

# 환경 변수 로드
load_dotenv()

# Supabase 설정
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def get_supabase_client() -> Client:
    """
    Supabase 클라이언트 인스턴스 반환
    
    Returns:
        Supabase Client 객체
    
    Raises:
        ValueError: SUPABASE_URL 또는 SUPABASE_KEY가 설정되지 않은 경우
    """
    if not SUPABASE_URL:
        raise DatabaseConnectionError(reason="SUPABASE_URL 환경 변수가 설정되지 않았습니다.")
    if not SUPABASE_KEY:
        raise DatabaseConnectionError(reason="SUPABASE_KEY 환경 변수가 설정되지 않았습니다.")
    
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Supabase 클라이언트 생성 실패: {e}", exc_info=True)
        raise DatabaseConnectionError(original_error=e)


# 싱글톤 인스턴스 (선택적)
_supabase_client: Optional[Client] = None


def get_client() -> Client:
    """
    싱글톤 패턴으로 Supabase 클라이언트 반환
    
    Returns:
        Supabase Client 객체
    """
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = get_supabase_client()
    return _supabase_client


def _split_storage_ref(storage_ref: str) -> tuple[str, str]:
    """
    storage_ref를 bucket/path로 분리합니다.
    
    Args:
        storage_ref: "bucket/path/to/file" 형식
    
    Returns:
        (bucket, path)
    """
    if "/" not in storage_ref:
        raise ValueError("storage_ref 형식이 올바르지 않습니다. 예: bucket/path/to/file")
    bucket, path = storage_ref.split("/", 1)
    return bucket, path


def download_storage_file(storage_ref: str) -> bytes:
    """
    Supabase Storage에서 파일 다운로드
    
    Args:
        storage_ref: "bucket/path/to/file" 형식
    
    Returns:
        파일 바이트
    """
    supabase = get_client()
    bucket, path = _split_storage_ref(storage_ref)
    return supabase.storage.from_(bucket).download(path)


def get_storage_public_url(storage_ref: str) -> str:
    """
    Supabase Storage 공개 URL 반환
    
    Args:
        storage_ref: "bucket/path/to/file" 형식
    
    Returns:
        공개 URL 문자열
    """
    supabase = get_client()
    bucket, path = _split_storage_ref(storage_ref)
    result = supabase.storage.from_(bucket).get_public_url(path)
    return result
