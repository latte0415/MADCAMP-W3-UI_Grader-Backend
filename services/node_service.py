"""노드 서비스"""
import json
from typing import Dict, Optional, Tuple, Union
from uuid import UUID
from playwright.async_api import Page

from infra.supabase import get_client, download_storage_file
from repositories import node_repository
from utils.hash_generator import (
    normalize_url,
    generate_storage_fingerprint,
    generate_state_hash,
    generate_a11y_hash,
    generate_content_dom_hash
)
from utils.state_collector import collect_page_state

STORAGE_BUCKET = "ui-artifacts"


class NodeService:
    """노드 관련 비즈니스 로직"""
    
    def __init__(self, node_repo=None):
        """
        Args:
            node_repo: NodeRepository 모듈 (기본값: node_repository)
        """
        self.node_repo = node_repo or node_repository
    
    def _upload_artifact(self, path: str, content: bytes, content_type: str) -> str:
        """
        Supabase Storage에 아티팩트 업로드
        
        Args:
            path: 저장 경로 (bucket 내부 경로)
            content: 업로드할 바이트 데이터
            content_type: MIME 타입
        
        Returns:
            저장된 객체 경로 (bucket/path)
        """
        supabase = get_client()
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=path,
            file=content,
            file_options={"content-type": content_type, "upsert": "true"}
        )
        return f"{STORAGE_BUCKET}/{path}"
    
    async def _collect_css_snapshot(self, page: Page) -> str:
        """
        페이지에서 접근 가능한 CSS 텍스트를 수집합니다.
        """
        return await page.evaluate(
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
    
    async def create_or_get_node(
        self,
        run_id: UUID,
        page: Page,
        depths: Optional[Dict[str, int]] = None,
        return_created: bool = False
    ) -> Union[Dict, Tuple[Dict, bool]]:
        """
        노드를 생성하거나 기존 노드를 반환합니다.
        
        UNIQUE 제약조건(run_id, url_normalized, a11y_hash, state_hash)으로
        중복을 자동 처리합니다.
        
        Args:
            run_id: 탐색 세션 ID
            page: Playwright Page 객체
            depths: depth 딕셔너리 (선택적)
            return_created: 생성 여부 반환 여부
        
        Returns:
            노드 정보 딕셔너리 또는 (노드, created 여부)
        
        Raises:
            Exception: Supabase 작업 실패 시
        """
        # 1. 페이지 상태 수집
        page_state = await collect_page_state(page)
        
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
        
        # 7. 기존 노드 확인 (Repository 사용)
        existing = self.node_repo.find_node_by_conditions(
            run_id, url_normalized, a11y_hash, state_hash
        )
        
        if existing:
            return (existing, False) if return_created else existing
        
        # 8. 노드 데이터 준비
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
        if depths:
            node_data.update({
                "route_depth": depths.get("route_depth"),
                "modal_depth": depths.get("modal_depth"),
                "interaction_depth": depths.get("interaction_depth")
            })
        
        # 9. 새 노드 생성 (Repository 사용)
        try:
            node = self.node_repo.create_node(node_data)
            node_id = node["id"]
            base_path = f"runs/{run_id}/nodes/{node_id}"
            
            # 10. 아티팩트 업로드 및 ref 업데이트
            # DOM 스냅샷 (HTML)
            dom_snapshot = await page.content()
            dom_ref = self._upload_artifact(
                f"{base_path}/dom_snapshot.html",
                dom_snapshot.encode("utf-8"),
                "text/html"
            )
            
            # CSS 스냅샷 (CSS)
            css_snapshot = await self._collect_css_snapshot(page)
            css_ref = self._upload_artifact(
                f"{base_path}/styles.css",
                css_snapshot.encode("utf-8"),
                "text/css"
            )
            
            # 접근성 정보 스냅샷 (a11y_info 방식, JSON)
            a11y_snapshot = a11y_info
            a11y_ref = self._upload_artifact(
                f"{base_path}/a11y_snapshot.json",
                json.dumps(a11y_snapshot, ensure_ascii=False).encode("utf-8"),
                "application/json"
            )
            
            # 스크린샷 (PNG)
            screenshot_bytes = await page.screenshot(type="png")
            screenshot_ref = self._upload_artifact(
                f"{base_path}/screenshot.png",
                screenshot_bytes,
                "image/png"
            )
            
            # storageState 원본 (JSON)
            storage_state_raw = await page.context.storage_state()
            storage_ref = self._upload_artifact(
                f"{base_path}/storage_state.json",
                json.dumps(storage_state_raw, ensure_ascii=False).encode("utf-8"),
                "application/json"
            )
            
            # refs 업데이트 (Repository 사용)
            updated_node = self.node_repo.update_node(node_id, {
                "dom_snapshot_ref": dom_ref,
                "css_snapshot_ref": css_ref,
                "a11y_snapshot_ref": a11y_ref,
                "screenshot_ref": screenshot_ref,
                "storage_ref": storage_ref
            })
            
            return (updated_node, True) if return_created else updated_node
            
        except Exception as e:
            error_msg = str(e)
            raise Exception(f"노드 삽입 실패: {error_msg}")
    
    def update_node_depths(self, node_id: UUID, depths: Dict[str, int]) -> Dict:
        """
        노드 depth 필드 업데이트
        
        Args:
            node_id: 노드 ID
            depths: depth 딕셔너리
        
        Returns:
            업데이트된 노드 정보 딕셔너리
        """
        return self.node_repo.update_node_depths(node_id, depths)
    
    def get_node_by_id(self, node_id: UUID) -> Optional[Dict]:
        """
        노드 ID로 노드 조회
        
        Args:
            node_id: 노드 ID
        
        Returns:
            노드 정보 딕셔너리 또는 None
        """
        return self.node_repo.get_node_by_id(node_id)
    
    def get_node_with_artifacts(self, node_id: UUID) -> Optional[Dict]:
        """
        노드 정보와 연결된 아티팩트(파일)를 함께 반환합니다.
        
        Args:
            node_id: 노드 ID
        
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
        node = self.get_node_by_id(node_id)
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


# 하위 호환성을 위한 함수 래퍼
_node_service_instance: Optional[NodeService] = None


def _get_node_service() -> NodeService:
    """싱글톤 NodeService 인스턴스 반환"""
    global _node_service_instance
    if _node_service_instance is None:
        _node_service_instance = NodeService()
    return _node_service_instance


async def create_or_get_node(
    run_id: UUID,
    page: Page,
    depths: Optional[Dict[str, int]] = None,
    return_created: bool = False
) -> Union[Dict, Tuple[Dict, bool]]:
    """하위 호환성을 위한 함수 래퍼"""
    return await _get_node_service().create_or_get_node(run_id, page, depths, return_created)


def update_node_depths(node_id: UUID, depths: Dict[str, int]) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_node_service().update_node_depths(node_id, depths)


def get_node_by_id(node_id: UUID) -> Optional[Dict]:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_node_service().get_node_by_id(node_id)


def get_node_with_artifacts(node_id: UUID) -> Optional[Dict]:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_node_service().get_node_with_artifacts(node_id)
