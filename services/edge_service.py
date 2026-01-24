"""엣지(액션) 서비스"""
import time
from typing import Dict, Optional
from uuid import UUID
from playwright.sync_api import Page

from infra.supabase import get_client
from services.node_service import create_or_get_node, get_node_by_id, update_node_depths
from utils.graph_classifier import classify_change, compute_next_depths


def is_duplicate_action(run_id: UUID, from_node_id: UUID, action: Dict) -> Optional[Dict]:
    """
    중복 액션 여부 확인
    
    Returns:
        기존 엣지 데이터 또는 None
    """
    supabase = get_client()
    action_value = action.get("action_value", "") or ""
    result = supabase.table("edges").select("*").eq("run_id", str(run_id)).eq(
        "from_node_id", str(from_node_id)
    ).eq("action_type", action["action_type"]).eq(
        "action_target", action["action_target"]
    ).eq("action_value", action_value).execute()

    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def perform_action(page: Page, action: Dict) -> Dict:
    """
    액션 수행
    
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
                page.wait_for_selector(selector, timeout=5000, state="attached")
                locator = page.locator(selector).first
                locator.evaluate("el => el.scrollIntoView({block: 'center'})")
                try:
                    locator.click(force=True, timeout=5000)
                except Exception:
                    # viewport 이슈 fallback: JS click
                    locator.evaluate("el => el.click()")
            elif role and name:
                locator = page.get_by_role(role, name=name)
                locator.evaluate("el => el.scrollIntoView({block: 'center'})")
                try:
                    locator.click(force=True, timeout=5000)
                except Exception:
                    locator.evaluate("el => el.click()")
            else:
                raise Exception("click: 대상 요소를 찾을 수 없습니다.")
            # URL 변경이 없으면 href로 직접 이동 시도
            if href and page.url == before_url:
                page.goto(href, wait_until="networkidle")
            # SPA에서 URL 변화 없이 DOM만 바뀌는 케이스 대비
            time.sleep(0.7)
        elif action_type == "hover":
            if role and name:
                page.get_by_role(role, name=name).hover()
            elif selector:
                page.hover(selector)
            else:
                raise Exception("hover: 대상 요소를 찾을 수 없습니다.")
            time.sleep(0.4)
        elif action_type == "fill":
            if selector:
                page.fill(selector, action_value)
            else:
                raise Exception("fill: 대상 요소를 찾을 수 없습니다.")
        elif action_type == "navigate":
            page.goto(action_value, wait_until="networkidle")
        elif action_type == "wait":
            page.wait_for_load_state("networkidle")
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
    """
    existing = is_duplicate_action(run_id, from_node_id, action)
    if existing:
        return existing

    supabase = get_client()
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

    result = supabase.table("edges").insert(edge_data).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]
    raise Exception("엣지 기록 실패: 데이터가 반환되지 않았습니다.")


def perform_and_record_edge(
    run_id: UUID,
    from_node_id: UUID,
    page: Page,
    action: Dict,
    depth_diff_type: Optional[str] = None
) -> Dict:
    """
    액션 수행 후 엣지 기록
    """
    existing = is_duplicate_action(run_id, from_node_id, action)
    if existing:
        return existing

    before_node = get_node_by_id(from_node_id)
    action_result = perform_action(page, action)

    to_node_id = None
    to_node = None
    to_node_created = False
    if action_result["outcome"] == "success":
        to_node, to_node_created = create_or_get_node(run_id, page, return_created=True)
        to_node_id = UUID(to_node["id"])
        print(f"[perform_and_record_edge] to_node_id={to_node_id}")
    else:
        print("[perform_and_record_edge] action failed; skip to_node")

    if depth_diff_type is None and before_node:
        depth_diff_type = classify_change(before_node, to_node, page)

    if to_node_created and before_node and depth_diff_type:
        depths = compute_next_depths(before_node, depth_diff_type)
        update_node_depths(to_node_id, depths)

    return record_edge(
        run_id=run_id,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        action=action,
        outcome=action_result["outcome"],
        latency_ms=action_result["latency_ms"],
        error_msg=action_result["error_msg"],
        depth_diff_type=depth_diff_type
    )
