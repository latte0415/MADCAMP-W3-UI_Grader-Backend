"""DOM 기반 액션 추출 유틸리티"""
from typing import Dict, List, Optional
from playwright.async_api import Page, ElementHandle


async def _get_role(element: ElementHandle) -> Optional[str]:
    role = await element.get_attribute("role")
    if role:
        return role
    tag = await element.evaluate("el => el.tagName.toLowerCase()")
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "input":
        input_type = await element.get_attribute("type") or "text"
        if input_type in ("submit", "button"):
            return "button"
        return "textbox"
    return None


async def _get_name(element: ElementHandle) -> str:
    aria_label = await element.get_attribute("aria-label")
    if aria_label:
        return aria_label.strip()
    placeholder = await element.get_attribute("placeholder")
    if placeholder:
        return placeholder.strip()
    try:
        text = (await element.inner_text()).strip()
        if text:
            return text
    except Exception:
        pass
    return ""


async def _build_selector(element: ElementHandle) -> str:
    tag = await element.evaluate("el => el.tagName.toLowerCase()")
    if tag == "a":
        href = await element.get_attribute("href")
        if href:
            return f"a[href='{href}']"
    element_id = await element.get_attribute("id")
    if element_id:
        return f"{tag}#{element_id}"
    name_attr = await element.get_attribute("name")
    if name_attr:
        return f"{tag}[name='{name_attr}']"
    class_attr = await element.get_attribute("class")
    if class_attr:
        class_list = class_attr.split()
        if class_list:
            first_class = class_list[0]
            return f"{tag}.{first_class}"
    return tag


async def _make_action(action_type: str, element: ElementHandle, action_value: Optional[str] = None) -> Dict:
    role = (await _get_role(element)) or ""
    name = await _get_name(element)
    selector = await _build_selector(element)
    tag = await element.evaluate("el => el.tagName.toLowerCase()")
    href = await element.get_attribute("href") if tag == "a" else None
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


async def extract_actions_from_page(page: Page) -> List[Dict]:
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
        elements = await page.query_selector_all(selector)
        for element in elements:
            try:
                if not await element.is_visible():
                    continue
            except Exception:
                pass
            actions.append(await _make_action("click", element))

    # Hover 후보 (메뉴/팝업 트리거로 추정되는 요소)
    hover_selectors = [
        "[aria-haspopup='true']",
        "[data-hover]",
        "[data-menu]",
        "nav a",
        "nav button"
    ]
    for selector in hover_selectors:
        elements = await page.query_selector_all(selector)
        for element in elements:
            try:
                if not await element.is_visible():
                    continue
            except Exception:
                pass
            actions.append(await _make_action("hover", element))

    # 입력 필드 fill
    fill_selectors = [
        "input[type='text']",
        "input[type='email']",
        "input[type='password']",
        "input[type='search']",
        "textarea"
    ]
    for selector in fill_selectors:
        elements = await page.query_selector_all(selector)
        for element in elements:
            try:
                if not await element.is_visible():
                    continue
            except Exception:
                pass
            actions.append(await _make_action("fill", element))

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
