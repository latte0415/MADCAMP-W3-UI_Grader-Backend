"""그래프 변화 타입 분류 유틸리티"""
from typing import Dict, Optional
from playwright.sync_api import Page


def _has_modal(page: Page) -> bool:
    return bool(page.query_selector("[role='dialog'], [aria-modal='true']"))


def _has_drawer(page: Page) -> bool:
    return bool(page.query_selector("[data-drawer], [data-sidebar], [aria-expanded='true']"))


def classify_change(
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
    if _has_modal(page):
        return "modal_overlay"
    if _has_drawer(page):
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
