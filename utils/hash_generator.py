"""해시 생성 유틸리티"""
import hashlib
import json
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from typing import Dict, Optional


def normalize_url(url: str) -> str:
    """
    URL을 정규화합니다.
    - 쿼리 파라미터 정렬
    - 해시(#) 제거 (SPA 라우팅은 별도 처리)
    - 프로토콜, 호스트, 경로 정규화
    """
    parsed = urlparse(url)
    
    # 쿼리 파라미터 정렬
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    sorted_query = urlencode(sorted(query_params.items()), doseq=True)
    
    # 해시 제거 (SPA 라우팅은 나중에 별도 처리)
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        '',  # params
        sorted_query,
        ''   # fragment (해시 제거)
    ))
    
    return normalized


def generate_storage_fingerprint(local_storage: Dict, session_storage: Dict) -> Dict:
    """
    스토리지 상태 지문 생성 (민감 정보 보호)
    
    Args:
        local_storage: localStorage 딕셔너리
        session_storage: sessionStorage 딕셔너리
    
    Returns:
        스토리지 지문 딕셔너리
    """
    fingerprint = {
        "local_keys": sorted(local_storage.keys()),
        "session_keys": sorted(session_storage.keys()),
        "hashed_values": {}
    }
    
    # 값의 해시만 저장 (원본 값은 저장하지 않음)
    for key in local_storage.keys():
        value = str(local_storage[key])
        fingerprint["hashed_values"][f"local_{key}"] = hashlib.sha256(value.encode()).hexdigest()
    
    for key in session_storage.keys():
        value = str(session_storage[key])
        fingerprint["hashed_values"][f"session_{key}"] = hashlib.sha256(value.encode()).hexdigest()
    
    return fingerprint


def generate_state_hash(auth_state: Dict, storage_fingerprint: Dict) -> str:
    """
    인증 상태와 스토리지 지문을 합쳐서 해시 생성
    
    Args:
        auth_state: 인증 상태 딕셔너리
        storage_fingerprint: 스토리지 지문 딕셔너리
    
    Returns:
        SHA-256 해시 문자열
    """
    # 상태를 정규화 (키 정렬)
    normalized_auth = json.dumps(auth_state, sort_keys=True)
    normalized_storage = json.dumps(storage_fingerprint, sort_keys=True)
    
    # 합쳐서 해시
    combined = f"{normalized_auth}|{normalized_storage}"
    return hashlib.sha256(combined.encode()).hexdigest()


def generate_a11y_hash(a11y_info: list) -> str:
    """
    접근성 정보 기반 해시 생성
    
    Args:
        a11y_info: 접근성 정보 리스트 (각 요소는 "role|label|name" 형식)
    
    Returns:
        SHA-256 해시 문자열
    """
    # 정렬 후 해시
    normalized = "|".join(sorted(a11y_info))
    return hashlib.sha256(normalized.encode()).hexdigest()


def generate_content_dom_hash(content_elements: list) -> Optional[str]:
    """
    콘텐츠 DOM 해시 생성 (선택적)
    
    Args:
        content_elements: 콘텐츠 요소 리스트 (텍스트 콘텐츠 중심)
    
    Returns:
        SHA-256 해시 문자열 또는 None
    """
    if not content_elements:
        return None
    
    # 정렬 후 해시
    normalized = "|".join(sorted(content_elements))
    return hashlib.sha256(normalized.encode()).hexdigest()
