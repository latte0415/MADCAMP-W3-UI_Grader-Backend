"""그래프 변화 타입 분류 유틸리티"""
from typing import Dict, Optional
from playwright.async_api import Page


async def _has_modal(page: Page) -> bool:
    element = await page.query_selector("[role='dialog'], [aria-modal='true']")
    return bool(element)


async def _has_drawer(page: Page) -> bool:
    element = await page.query_selector("[data-drawer], [data-sidebar], [aria-expanded='true']")
    return bool(element)


async def classify_change(
    before_node: Dict,
    after_node: Optional[Dict],
    page: Page
) -> str:
    """
    액션 전/후 상태를 비교해 변화 타입을 분류합니다.
    
    Returns:
        same_node / interaction_only / new_page / modal_overlay / drawer
    """
    if not after_node:
        return "interaction_only"

    before_url = before_node.get("url_normalized") or before_node.get("url")
    after_url = after_node.get("url_normalized") or after_node.get("url")
    if before_url and after_url and before_url != after_url:
        return "new_page"

    # overlay/drawer 힌트 우선
    if await _has_modal(page):
        return "modal_overlay"
    if await _has_drawer(page):
        return "drawer"

    # 동일 노드인지 확인
    if before_node.get("id") == after_node.get("id"):
        return "same_node"

    # 해시가 동일하면 same_node
    if before_node.get("a11y_hash") == after_node.get("a11y_hash") and \
       before_node.get("state_hash") == after_node.get("state_hash") and \
       before_node.get("content_dom_hash") == after_node.get("content_dom_hash"):
        return "same_node"

    return "interaction_only"


def compute_next_depths(before_node: Optional[Dict], depth_diff_type: str) -> Dict[str, int]:
    """
    depth_diff_type에 따라 다음 노드의 depth를 계산합니다.
    """
    base_route = int((before_node or {}).get("route_depth") or 0)
    base_modal = int((before_node or {}).get("modal_depth") or 0)
    base_interaction = int((before_node or {}).get("interaction_depth") or 0)

    route_depth = base_route
    modal_depth = base_modal
    interaction_depth = base_interaction

    if depth_diff_type == "new_page":
        route_depth += 1
    elif depth_diff_type in ("modal_overlay", "drawer"):
        modal_depth += 1
    elif depth_diff_type == "interaction_only":
        interaction_depth += 1

    return {
        "route_depth": route_depth,
        "modal_depth": modal_depth,
        "interaction_depth": interaction_depth
    }
