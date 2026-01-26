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
    if tag == "a":
        href = element.get_attribute("href")
        if href:
            return f"a[href='{href}']"
    element_id = element.get_attribute("id")
    if element_id:
        return f"{tag}#{element_id}"
    name_attr = element.get_attribute("name")
    if name_attr:
        return f"{tag}[name='{name_attr}']"
    class_attr = element.get_attribute("class")
    if class_attr:
        class_list = class_attr.split()
        if class_list:
            first_class = class_list[0]
            return f"{tag}.{first_class}"
    return tag


def _make_action(action_type: str, element: ElementHandle, action_value: Optional[str] = None) -> Dict:
    role = _get_role(element) or ""
    name = _get_name(element)
    selector = _build_selector(element)
    tag = element.evaluate("el => el.tagName.toLowerCase()")
    href = element.get_attribute("href") if tag == "a" else None
    action_target = f"role={role} name={name}".strip()
    if not role and not name:
        action_target = selector

    return {
        "action_type": action_type,
        "action_target": action_target,
        "role": role,
        "name": name,
        "selector": selector,
        "action_value": action_value or "",
        "tag": tag,
        "href": href
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
            try:
                if not element.is_visible():
                    continue
            except Exception:
                pass
            actions.append(_make_action("click", element))

    # Hover 후보 (메뉴/팝업 트리거로 추정되는 요소)
    hover_selectors = [
        "[aria-haspopup='true']",
        "[data-hover]",
        "[data-menu]",
        "nav a",
        "nav button"
    ]
    for selector in hover_selectors:
        for element in page.query_selector_all(selector):
            try:
                if not element.is_visible():
                    continue
            except Exception:
                pass
            actions.append(_make_action("hover", element))

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
            try:
                if not element.is_visible():
                    continue
            except Exception:
                pass
            actions.append(_make_action("fill", element))

    # 중복 제거 (action_type + action_target + action_value)
    deduped: Dict[str, Dict] = {}
    for action in actions:
        key = f"{action['action_type']}|{action['action_target']}|{action['action_value']}"
        deduped[key] = action

    return list(deduped.values())


def filter_input_required_actions(actions: List[Dict]) -> List[Dict]:
    """
    입력 정보가 필요한 액션만 필터링합니다.
    - 텍스트 입력, 드롭다운, 토글 등 포함
    """
    input_roles = {
        "textbox",
        "combobox",
        "listbox",
        "switch",
        "checkbox",
        "radio",
        "spinbutton",
        "slider"
    }
    input_tags = {"input", "textarea", "select"}
    filtered: List[Dict] = []

    for action in actions:
        action_type = action.get("action_type", "")
        role = (action.get("role") or "").lower()
        tag = (action.get("tag") or "").lower()
        selector = (action.get("selector") or "").lower()

        if action_type == "fill":
            filtered.append(action)
            continue
        if role in input_roles:
            filtered.append(action)
            continue
        if tag in input_tags:
            filtered.append(action)
            continue
        if selector.startswith(("input", "textarea", "select")):
            filtered.append(action)
            continue

    return filtered
