"""노드 삽입 서비스"""
import json
from typing import Dict, Optional
from uuid import UUID
from playwright.sync_api import Page
import os 
import sys 

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)


from infra.supabase import get_client, download_storage_file
from utils.hash_generator import (
    normalize_url,
    generate_storage_fingerprint,
    generate_state_hash,
    generate_a11y_hash,
    generate_content_dom_hash
)
from utils.state_collector import collect_page_state

STORAGE_BUCKET = "ui-artifacts"


def _upload_artifact(supabase, path: str, content: bytes, content_type: str) -> str:
    """
    Supabase Storage에 아티팩트 업로드
    
    Args:
        supabase: Supabase client
        path: 저장 경로 (bucket 내부 경로)
        content: 업로드할 바이트 데이터
        content_type: MIME 타입
    
    Returns:
        저장된 객체 경로 (bucket/path)
    """
    supabase.storage.from_(STORAGE_BUCKET).upload(
        path=path,
        file=content,
        file_options={"content-type": content_type, "upsert": "true"}
    )
    return f"{STORAGE_BUCKET}/{path}"


def _collect_css_snapshot(page: Page) -> str:
    """
    페이지에서 접근 가능한 CSS 텍스트를 수집합니다.
    """
    return page.evaluate(
        """
        () => {
            const cssTexts = [];
            for (const sheet of Array.from(document.styleSheets || [])) {
                try {
                    const rules = sheet.cssRules;
                    if (!rules) continue;
                    for (const rule of Array.from(rules)) {
                        cssTexts.push(rule.cssText);
                    }
                } catch (e) {
                    // CORS 등으로 접근 불가한 스타일시트는 건너뜀
                    continue;
                }
            }
            return cssTexts.join("\\n");
        }
        """
    )


# NOTE: 접근성 스냅샷 수집은 현재 사용하지 않습니다.
# def _collect_a11y_snapshot(page: Page) -> Dict:
#     """
#     접근성 스냅샷 수집 (실패 시 재시도)
#     """
#     try:
#         page.wait_for_load_state("domcontentloaded", timeout=5000)
#     except Exception:
#         # load state 대기 실패는 무시하고 계속 시도
#         pass
#
#     def _snapshot_via_playwright() -> Dict:
#         snapshot = page.accessibility.snapshot(interesting_only=False)
#         return snapshot or {"error": "accessibility snapshot empty"}
#
#     def _snapshot_via_cdp() -> Dict:
#         session = page.context.new_cdp_session(page)
#         result = session.send("Accessibility.getFullAXTree")
#         return result or {"error": "accessibility snapshot empty"}
#
#     # 1) Playwright API 우선 시도 (버전에 따라 attribute가 없을 수 있음)
#     if hasattr(page, "accessibility"):
#         try:
#             return _snapshot_via_playwright()
#         except Exception:
#             pass
#
#     # 2) CDP fallback (Chromium 계열에서만 동작)
#     try:
#         return _snapshot_via_cdp()
#     except Exception:
#         try:
#             page.wait_for_timeout(300)
#             if hasattr(page, "accessibility"):
#                 return _snapshot_via_playwright()
#             return _snapshot_via_cdp()
#         except Exception as retry_error:
#             return {
#                 "error": "accessibility snapshot failed",
#                 "error_detail": str(retry_error)
#             }


def create_or_get_node(run_id: UUID, page: Page) -> Dict:
    """
    노드를 생성하거나 기존 노드를 반환합니다.
    
    UNIQUE 제약조건(run_id, url_normalized, a11y_hash, state_hash)으로
    중복을 자동 처리합니다.
    
    Args:
        run_id: 탐색 세션 ID
        page: Playwright Page 객체
    
    Returns:
        노드 정보 딕셔너리 (id 포함)
    
    Raises:
        Exception: Supabase 작업 실패 시
    """
    # 1. 페이지 상태 수집
    page_state = collect_page_state(page)
    
    # 2. URL 정규화
    url = page_state["url"]
    url_normalized = normalize_url(url)
    
    # 3. 스토리지 지문 생성
    storage_state = page_state["storage_state"]
    storage_fingerprint = generate_storage_fingerprint(
        storage_state.get("localStorage", {}),
        storage_state.get("sessionStorage", {})
    )
    
    # 4. 상태 해시 생성
    auth_state = page_state["auth_state"]
    state_hash = generate_state_hash(auth_state, storage_fingerprint)
    
    # 5. 접근성 해시 생성
    a11y_info = page_state["a11y_info"]
    a11y_hash = generate_a11y_hash(a11y_info)
    
    # 6. 콘텐츠 DOM 해시 생성 (선택적)
    content_elements = page_state["content_elements"]
    content_dom_hash = generate_content_dom_hash(content_elements)
    
    # 7. 노드 데이터 준비
    node_data = {
        "run_id": str(run_id),
        "url": url,
        "url_normalized": url_normalized,
        "a11y_hash": a11y_hash,
        "content_dom_hash": content_dom_hash,
        "state_hash": state_hash,
        "auth_state": auth_state,
        "storage_fingerprint": storage_fingerprint,
        # 원본 파일 참조는 나중에 구현 (현재는 NULL)
        "dom_snapshot_ref": None,
        "a11y_snapshot_ref": None,
        "screenshot_ref": None,
        "storage_ref": None,
        "css_snapshot_ref": None
    }
    
    # 8. Supabase에 삽입 시도
    supabase = get_client()
    
    try:
        # 기존 노드 확인 (동치 조건)
        existing = supabase.table("nodes").select("*").eq("run_id", str(run_id)).eq(
            "url_normalized", url_normalized
        ).eq("a11y_hash", a11y_hash).eq("state_hash", state_hash).execute()
        
        if existing.data and len(existing.data) > 0:
            return existing.data[0]
        
        # 새 노드 생성
        result = supabase.table("nodes").insert(node_data).execute()
        
        if result.data and len(result.data) > 0:
            node = result.data[0]
            
            # 9. 아티팩트 업로드 및 ref 업데이트
            node_id = node["id"]
            base_path = f"runs/{run_id}/nodes/{node_id}"
            
            # DOM 스냅샷 (HTML)
            dom_snapshot = page.content()
            dom_ref = _upload_artifact(
                supabase,
                f"{base_path}/dom_snapshot.html",
                dom_snapshot.encode("utf-8"),
                "text/html"
            )

            # CSS 스냅샷 (CSS)
            css_snapshot = _collect_css_snapshot(page)
            css_ref = _upload_artifact(
                supabase,
                f"{base_path}/styles.css",
                css_snapshot.encode("utf-8"),
                "text/css"
            )
            
            # 접근성 정보 스냅샷 (a11y_info 방식, JSON)
            a11y_snapshot = a11y_info
            a11y_ref = _upload_artifact(
                supabase,
                f"{base_path}/a11y_snapshot.json",
                json.dumps(a11y_snapshot, ensure_ascii=False).encode("utf-8"),
                "application/json"
            )
            
            # 스크린샷 (PNG)
            screenshot_bytes = page.screenshot(type="png")
            screenshot_ref = _upload_artifact(
                supabase,
                f"{base_path}/screenshot.png",
                screenshot_bytes,
                "image/png"
            )
            
            # storageState 원본 (JSON)
            storage_state_raw = page.context.storage_state()
            storage_ref = _upload_artifact(
                supabase,
                f"{base_path}/storage_state.json",
                json.dumps(storage_state_raw, ensure_ascii=False).encode("utf-8"),
                "application/json"
            )
            
            # refs 업데이트
            update_result = supabase.table("nodes").update({
                "dom_snapshot_ref": dom_ref,
                "css_snapshot_ref": css_ref,
                "a11y_snapshot_ref": a11y_ref,
                "screenshot_ref": screenshot_ref,
                "storage_ref": storage_ref
            }).eq("id", node_id).execute()
            
            if update_result.data and len(update_result.data) > 0:
                return update_result.data[0]
            return node
        else:
            raise Exception("노드 삽입 실패: 데이터가 반환되지 않았습니다.")
            
    except Exception as e:
        error_msg = str(e)
        raise Exception(f"노드 삽입 실패: {error_msg}")


def get_node_by_id(node_id: UUID) -> Optional[Dict]:
    """
    노드 ID로 노드 조회
    
    Args:
        node_id: 노드 ID
    
    Returns:
        노드 정보 딕셔너리 또는 None
    """
    supabase = get_client()
    result = supabase.table("nodes").select("*").eq("id", str(node_id)).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def get_node_with_artifacts(node_id: UUID) -> Optional[Dict]:
    """
    노드 정보와 연결된 아티팩트(파일)를 함께 반환합니다.
    
    Returns:
        {
            ...node_fields,
            "artifacts": {
                "dom_snapshot_html": str | None,
                "a11y_snapshot": dict | None,
                "screenshot_bytes": bytes | None,
                "storage_state": dict | None
            }
        }
    """
    node = get_node_by_id(node_id)
    if not node:
        return None
    
    artifacts = {
        "dom_snapshot_html": None,
        "css_snapshot": None,
        "a11y_snapshot": None,
        "screenshot_bytes": None,
        "storage_state": None
    }
    
    # DOM 스냅샷 (HTML)
    if node.get("dom_snapshot_ref"):
        dom_bytes = download_storage_file(node["dom_snapshot_ref"])
        artifacts["dom_snapshot_html"] = dom_bytes.decode("utf-8", errors="replace")

    # CSS 스냅샷 (CSS)
    if node.get("css_snapshot_ref"):
        css_bytes = download_storage_file(node["css_snapshot_ref"])
        artifacts["css_snapshot"] = css_bytes.decode("utf-8", errors="replace")
    
    # 접근성 스냅샷 (JSON)
    if node.get("a11y_snapshot_ref"):
        a11y_bytes = download_storage_file(node["a11y_snapshot_ref"])
        artifacts["a11y_snapshot"] = json.loads(a11y_bytes.decode("utf-8"))
    
    # 스크린샷 (PNG bytes)
    if node.get("screenshot_ref"):
        artifacts["screenshot_bytes"] = download_storage_file(node["screenshot_ref"])
    
    # storageState 원본 (JSON)
    if node.get("storage_ref"):
        storage_bytes = download_storage_file(node["storage_ref"])
        artifacts["storage_state"] = json.loads(storage_bytes.decode("utf-8"))
    
    node["artifacts"] = artifacts
    return node
