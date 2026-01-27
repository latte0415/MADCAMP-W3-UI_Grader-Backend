"""DOM 기반 액션 추출 유틸리티"""
import re
from typing import Dict, List, Optional, Tuple
from playwright.async_api import Page, ElementHandle


def parse_action_target(action_target: str) -> Tuple[Optional[str], Optional[str]]:
    """
    action_target 문자열에서 role과 name을 파싱합니다.
    
    Args:
        action_target: "role=textbox name=E-mail" 형식의 문자열
    
    Returns:
        (role, name) 튜플
    """
    if not action_target:
        return None, None
    
    role_match = re.search(r"role=([^\s]+)", action_target)
    name_match = re.search(r"name=(.+)", action_target)
    
    role = role_match.group(1) if role_match else None
    name = name_match.group(1).strip() if name_match else None
    
    return role, name


async def _get_role(element: ElementHandle) -> Optional[str]:
    """요소의 ARIA role 또는 태그/타입 기반 추론 role 반환."""
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
    """aria-label, placeholder, inner_text 순으로 요소 이름 추출."""
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
    """href/id/name/class 순으로 CSS selector 생성."""
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
    """요소로부터 action_type에 맞는 액션 딕셔너리 생성."""
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


async def _is_element_interactable(element: ElementHandle) -> bool:
    """
    요소가 실제로 상호작용 가능한지 확인
    
    Returns:
        True if element is visible, enabled, and interactable
    """
    try:
        # 요소가 DOM에 존재하는지 확인
        # is_connected 체크를 위해 evaluate 사용
        is_connected = await element.evaluate("el => el.isConnected")
        if not is_connected:
            return False
        
        # 요소가 보이는지 확인
        if not await element.is_visible():
            return False
        
        # Playwright의 is_enabled() 메서드 사용 (가장 정확함)
        if not await element.is_enabled():
            return False
        
        # disabled 속성 확인 (추가 안전장치)
        is_disabled = await element.get_attribute("disabled")
        if is_disabled is not None:
            return False
        
        # aria-disabled 속성 확인
        aria_disabled = await element.get_attribute("aria-disabled")
        if aria_disabled == "true":
            return False
        
        # pointer-events가 none인지 확인
        pointer_events = await element.evaluate("el => window.getComputedStyle(el).pointerEvents")
        if pointer_events == "none":
            return False
        
        return True
    except Exception:
        # 예외 발생 시 요소가 존재하지 않거나 접근 불가능한 것으로 간주
        return False


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
            # 요소가 상호작용 가능한지 확인
            if not await _is_element_interactable(element):
                continue
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
            # 요소가 상호작용 가능한지 확인
            if not await _is_element_interactable(element):
                continue
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
            # 요소가 상호작용 가능한지 확인
            if not await _is_element_interactable(element):
                continue
            # 입력 필드는 추가로 편집 가능한지 확인
            try:
                is_readonly = await element.get_attribute("readonly")
                if is_readonly is not None:
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
