"""엣지(액션) 서비스"""
import time
from typing import Dict, Optional
from uuid import UUID
from playwright.async_api import Page

from repositories import edge_repository
from repositories import node_repository
from utils.graph_classifier import classify_change, compute_next_depths


class EdgeService:
    """엣지 관련 비즈니스 로직"""
    
    def __init__(self, edge_repo=None, node_repo=None, node_service=None):
        """
        Args:
            edge_repo: EdgeRepository 모듈 (기본값: edge_repository)
            node_repo: NodeRepository 모듈 (기본값: node_repository)
            node_service: NodeService 인스턴스 (선택적)
        """
        self.edge_repo = edge_repo or edge_repository
        self.node_repo = node_repo or node_repository
        self.node_service = node_service
    
    def is_duplicate_action(self, run_id: UUID, from_node_id: UUID, action: Dict) -> Optional[Dict]:
        """
        중복 액션 여부 확인
        
        Args:
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
            action: 액션 딕셔너리
        
        Returns:
            기존 엣지 데이터 또는 None
        """
        action_value = action.get("action_value", "") or ""
        return self.edge_repo.find_duplicate_edge(
            run_id,
            from_node_id,
            action["action_type"],
            action["action_target"],
            action_value
        )
    
    async def perform_action(self, page: Page, action: Dict) -> Dict:
        """
        액션 수행
        
        Args:
            page: Playwright Page 객체
            action: 액션 딕셔너리
        
        Returns:
            {outcome, latency_ms, error_msg}
        """
        start_time = time.time()
        error_msg = None
        outcome = "success"
        
        try:
            action_type = action["action_type"]
            action_value = action.get("action_value", "")
            role = action.get("role")
            name = action.get("name")
            selector = action.get("selector")
            before_url = page.url
            print(f"[perform_action] type={action_type} role={role} name={name} selector={selector} url={before_url}")
            
            if action_type == "click":
                href = action.get("href")
                if selector:
                    await page.wait_for_selector(selector, timeout=5000, state="attached")
                    locator = page.locator(selector).first
                    await locator.evaluate("el => el.scrollIntoView({block: 'center'})")
                    try:
                        await locator.click(force=True, timeout=5000)
                    except Exception:
                        # viewport 이슈 fallback: JS click
                        await locator.evaluate("el => el.click()")
                elif role and name:
                    locator = page.get_by_role(role, name=name)
                    await locator.evaluate("el => el.scrollIntoView({block: 'center'})")
                    try:
                        await locator.click(force=True, timeout=5000)
                    except Exception:
                        await locator.evaluate("el => el.click()")
                else:
                    raise Exception("click: 대상 요소를 찾을 수 없습니다.")
                # URL 변경이 없으면 href로 직접 이동 시도
                if href and page.url == before_url:
                    await page.goto(href, wait_until="networkidle")
                # SPA에서 URL 변화 없이 DOM만 바뀌는 케이스 대비
                await page.wait_for_timeout(700)
            elif action_type == "hover":
                if role and name:
                    await page.get_by_role(role, name=name).hover()
                elif selector:
                    await page.hover(selector)
                else:
                    raise Exception("hover: 대상 요소를 찾을 수 없습니다.")
                await page.wait_for_timeout(400)
            elif action_type == "fill":
                if selector:
                    await page.fill(selector, action_value)
                else:
                    raise Exception("fill: 대상 요소를 찾을 수 없습니다.")
            elif action_type == "navigate":
                await page.goto(action_value, wait_until="networkidle")
            elif action_type == "wait":
                await page.wait_for_load_state("networkidle")
            else:
                raise Exception(f"알 수 없는 action_type: {action_type}")
            after_url = page.url
            print(f"[perform_action] done url={after_url}")
        except Exception as e:
            outcome = "fail"
            error_msg = str(e)
            print(f"[perform_action] error={error_msg}")
        
        latency_ms = int((time.time() - start_time) * 1000)
        return {"outcome": outcome, "latency_ms": latency_ms, "error_msg": error_msg}
    
    def record_edge(
        self,
        run_id: UUID,
        from_node_id: UUID,
        to_node_id: Optional[UUID],
        action: Dict,
        outcome: str,
        latency_ms: int,
        error_msg: Optional[str] = None,
        depth_diff_type: Optional[str] = None
    ) -> Dict:
        """
        엣지 기록 (중복 검사 포함)
        
        Args:
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
            to_node_id: 종료 노드 ID (선택적)
            action: 액션 딕셔너리
            outcome: 결과 ('success' 또는 'fail')
            latency_ms: 지연 시간 (밀리초)
            error_msg: 에러 메시지 (선택적)
            depth_diff_type: depth 차이 타입 (선택적)
        
        Returns:
            엣지 정보 딕셔너리
        """
        existing = self.is_duplicate_action(run_id, from_node_id, action)
        if existing:
            return existing
        
        action_value = action.get("action_value", "") or ""
        edge_data = {
            "run_id": str(run_id),
            "from_node_id": str(from_node_id),
            "to_node_id": str(to_node_id) if to_node_id else None,
            "action_type": action["action_type"],
            "action_target": action["action_target"],
            "action_value": action_value,
            "cost": action.get("cost", 1),
            "latency_ms": latency_ms,
            "outcome": outcome,
            "error_msg": error_msg,
            "depth_diff_type": depth_diff_type
        }
        
        return self.edge_repo.create_edge(edge_data)
    
    async def perform_and_record_edge(
        self,
        run_id: UUID,
        from_node_id: UUID,
        page: Page,
        action: Dict,
        depth_diff_type: Optional[str] = None
    ) -> Dict:
        """
        액션 수행 후 엣지 기록
        
        Args:
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
            page: Playwright Page 객체
            action: 액션 딕셔너리
            depth_diff_type: depth 차이 타입 (선택적)
        
        Returns:
            엣지 정보 딕셔너리
        """
        existing = self.is_duplicate_action(run_id, from_node_id, action)
        if existing:
            return existing
        
        # node_service가 주입된 경우 사용, 없으면 node_repo 직접 사용
        before_node = None
        if self.node_service:
            before_node = self.node_service.get_node_by_id(from_node_id)
        else:
            before_node = self.node_repo.get_node_by_id(from_node_id)
        
        action_result = await self.perform_action(page, action)
        
        to_node_id = None
        to_node = None
        to_node_created = False
        if action_result["outcome"] == "success":
            if self.node_service:
                result = await self.node_service.create_or_get_node(run_id, page, return_created=True)
                if isinstance(result, tuple):
                    to_node, to_node_created = result
                else:
                    to_node = result
                    to_node_created = False
            else:
                # node_service가 없으면 직접 호출 (하위 호환성)
                from services.node_service import create_or_get_node
                result = await create_or_get_node(run_id, page, return_created=True)
                if isinstance(result, tuple):
                    to_node, to_node_created = result
                else:
                    to_node = result
                    to_node_created = False
            
            to_node_id = UUID(to_node["id"])
            print(f"[perform_and_record_edge] to_node_id={to_node_id}")
        else:
            print("[perform_and_record_edge] action failed; skip to_node")
        
        if depth_diff_type is None and before_node:
            depth_diff_type = await classify_change(before_node, to_node, page)
        
        if to_node_created and before_node and depth_diff_type:
            depths = compute_next_depths(before_node, depth_diff_type)
            if self.node_service:
                self.node_service.update_node_depths(to_node_id, depths)
            else:
                self.node_repo.update_node_depths(to_node_id, depths)
        
        return self.record_edge(
            run_id=run_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            action=action,
            outcome=action_result["outcome"],
            latency_ms=action_result["latency_ms"],
            error_msg=action_result["error_msg"],
            depth_diff_type=depth_diff_type
        )


# 하위 호환성을 위한 함수 래퍼
_edge_service_instance: Optional[EdgeService] = None


def _get_edge_service() -> EdgeService:
    """싱글톤 EdgeService 인스턴스 반환"""
    global _edge_service_instance
    if _edge_service_instance is None:
        _edge_service_instance = EdgeService()
    return _edge_service_instance


def is_duplicate_action(run_id: UUID, from_node_id: UUID, action: Dict) -> Optional[Dict]:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_edge_service().is_duplicate_action(run_id, from_node_id, action)


async def perform_action(page: Page, action: Dict) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return await _get_edge_service().perform_action(page, action)


def record_edge(
    run_id: UUID,
    from_node_id: UUID,
    to_node_id: Optional[UUID],
    action: Dict,
    outcome: str,
    latency_ms: int,
    error_msg: Optional[str] = None,
    depth_diff_type: Optional[str] = None
) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_edge_service().record_edge(
        run_id, from_node_id, to_node_id, action, outcome, latency_ms, error_msg, depth_diff_type
    )


async def perform_and_record_edge(
    run_id: UUID,
    from_node_id: UUID,
    page: Page,
    action: Dict,
    depth_diff_type: Optional[str] = None
) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return await _get_edge_service().perform_and_record_edge(
        run_id, from_node_id, page, action, depth_diff_type
    )
