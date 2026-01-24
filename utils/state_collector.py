"""웹페이지 상태 수집 유틸리티"""
from typing import Dict, List, Optional
from playwright.sync_api import Page


def collect_storage_state(page: Page) -> Dict[str, Dict]:
    """
    localStorage와 sessionStorage 상태 수집
    
    Args:
        page: Playwright Page 객체
    
    Returns:
        {"localStorage": {...}, "sessionStorage": {...}} 딕셔너리
    """
    local_storage = page.evaluate("() => ({ ...localStorage })")
    session_storage = page.evaluate("() => ({ ...sessionStorage })")
    
    return {
        "localStorage": local_storage or {},
        "sessionStorage": session_storage or {}
    }


def infer_auth_state(storage_state: Dict[str, Dict]) -> Dict:
    """
    스토리지 상태에서 인증 상태 추론
    
    Args:
        storage_state: collect_storage_state()의 반환값
    
    Returns:
        인증 상태 딕셔너리 {is_logged_in, user_role, has_token, ...}
    """
    auth_state = {
        "is_logged_in": False,
        "has_token": False,
        "user_role": None,
        "plan": None,
        "tenant": None
    }
    
    # localStorage와 sessionStorage에서 토큰 관련 키 찾기
    local_storage = storage_state.get("localStorage", {})
    session_storage = storage_state.get("sessionStorage", {})
    
    # 토큰 존재 여부 확인 (일반적인 토큰 키 이름들)
    token_keys = ["token", "access_token", "auth_token", "jwt", "accessToken", "authToken"]
    all_storage = {**local_storage, **session_storage}
    
    for key in token_keys:
        if key.lower() in [k.lower() for k in all_storage.keys()]:
            auth_state["has_token"] = True
            auth_state["is_logged_in"] = True
            break
    
    # user_role, plan, tenant 등 추론
    for key, value in all_storage.items():
        key_lower = key.lower()
        if "role" in key_lower:
            auth_state["user_role"] = value
        elif "plan" in key_lower:
            auth_state["plan"] = value
        elif "tenant" in key_lower:
            auth_state["tenant"] = value
    
    return auth_state


def collect_a11y_info(page: Page) -> List[str]:
    """
    접근성 정보 수집
    
    Args:
        page: Playwright Page 객체
    
    Returns:
        접근성 정보 리스트 (각 요소는 "role|label|name" 형식)
    """
    a11y_info = []
    
    # ARIA 속성, 역할, 이름 등 접근성 정보 수집
    elements = page.query_selector_all("[role], [aria-label], [aria-labelledby], button, a, input, select, textarea")
    
    for element in elements:
        try:
            role = element.get_attribute("role") or ""
            label = element.get_attribute("aria-label") or ""
            labelledby = element.get_attribute("aria-labelledby") or ""
            
            # 텍스트 콘텐츠 가져오기 (처음 50자만)
            try:
                name = element.inner_text().strip()[:50]
            except:
                name = ""
            
            # labelledby가 있으면 해당 요소의 텍스트도 가져오기
            if labelledby:
                try:
                    labelled_element = page.query_selector(f"#{labelledby}")
                    if labelled_element:
                        name = labelled_element.inner_text().strip()[:50]
                except:
                    pass
            
            # 의미있는 정보가 있을 때만 추가
            if role or label or name:
                a11y_info.append(f"{role}|{label}|{name}")
        except:
            # 요소 접근 실패 시 스킵
            continue
    
    return a11y_info


def collect_content_elements(page: Page) -> List[str]:
    """
    콘텐츠 요소 수집 (텍스트 콘텐츠 중심)
    
    Args:
        page: Playwright Page 객체
    
    Returns:
        콘텐츠 요소 리스트
    """
    content_elements = []
    
    # 주요 콘텐츠 요소 선택자
    selectors = [
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "span", "div[class*='content']", "main", "article"
    ]
    
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
            for element in elements[:10]:  # 각 타입당 최대 10개만
                try:
                    text = element.inner_text().strip()
                    if text and len(text) > 5:  # 최소 5자 이상
                        content_elements.append(f"{selector}:{text[:100]}")  # 처음 100자만
                except:
                    continue
        except:
            continue
    
    return content_elements


def collect_page_state(page: Page) -> Dict:
    """
    웹페이지 상태 수집
    
    Args:
        page: Playwright Page 객체
    
    Returns:
        페이지 상태 딕셔너리
    """
    # URL 수집
    url = page.url
    
    # 스토리지 상태 수집
    storage_state = collect_storage_state(page)
    
    # 인증 상태 추론
    auth_state = infer_auth_state(storage_state)
    
    # 접근성 정보 수집
    a11y_info = collect_a11y_info(page)
    
    # 콘텐츠 요소 수집 (선택적)
    content_elements = collect_content_elements(page)
    
    return {
        "url": url,
        "storage_state": storage_state,
        "auth_state": auth_state,
        "a11y_info": a11y_info,
        "content_elements": content_elements
    }
