"""DOM 기반 액션 추출 유틸리티"""
from typing import Dict, List, Optional
from playwright.sync_api import Page, ElementHandle


def _get_role(element: ElementHandle) -> Optional[str]:
    role = element.get_attribute("role")
    if role:
        return role
    tag = element.evaluate("el => el.tagName.toLowerCase()")
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "input":
        input_type = element.get_attribute("type") or "text"
        if input_type in ("submit", "button"):
            return "button"
        return "textbox"
    return None


def _get_name(element: ElementHandle) -> str:
    aria_label = element.get_attribute("aria-label")
    if aria_label:
        return aria_label.strip()
    placeholder = element.get_attribute("placeholder")
    if placeholder:
        return placeholder.strip()
    try:
        text = element.inner_text().strip()
        if text:
            return text
    except Exception:
        pass
    return ""


def _build_selector(element: ElementHandle) -> str:
    tag = element.evaluate("el => el.tagName.toLowerCase()")
    element_id = element.get_attribute("id")
    if element_id:
        return f"{tag}#{element_id}"
    name_attr = element.get_attribute("name")
    if name_attr:
        return f"{tag}[name='{name_attr}']"
    class_attr = element.get_attribute("class")
    if class_attr:
        first_class = class_attr.split()[0]
        return f"{tag}.{first_class}"
    return tag


def _make_action(action_type: str, element: ElementHandle, action_value: Optional[str] = None) -> Dict:
    role = _get_role(element) or ""
    name = _get_name(element)
    selector = _build_selector(element)
    action_target = f"role={role} name={name}".strip()
    if not role and not name:
        action_target = selector

    return {
        "action_type": action_type,
        "action_target": action_target,
        "role": role,
        "name": name,
        "selector": selector,
        "action_value": action_value or ""
    }


def extract_actions_from_page(page: Page) -> List[Dict]:
    """
    DOM 스캔으로 가능한 액션 추출
    
    Returns:
        action dict list
    """
    actions: List[Dict] = []

    # 버튼/링크 클릭
    click_selectors = [
        "button",
        "a",
        "input[type='button']",
        "input[type='submit']"
    ]
    for selector in click_selectors:
        for element in page.query_selector_all(selector):
            actions.append(_make_action("click", element))

    # 입력 필드 fill
    fill_selectors = [
        "input[type='text']",
        "input[type='email']",
        "input[type='password']",
        "input[type='search']",
        "textarea"
    ]
    for selector in fill_selectors:
        for element in page.query_selector_all(selector):
            actions.append(_make_action("fill", element))

    # 중복 제거 (action_type + action_target + action_value)
    deduped: Dict[str, Dict] = {}
    for action in actions:
        key = f"{action['action_type']}|{action['action_target']}|{action['action_value']}"
        deduped[key] = action

    return list(deduped.values())
