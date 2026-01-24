"""엣지(액션) 서비스"""
import time
from typing import Dict, Optional
from uuid import UUID
from playwright.sync_api import Page

from infra.supabase import get_client
from services.node_service import create_or_get_node, get_node_by_id
from utils.graph_classifier import classify_change


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

        if action_type == "click":
            if role and name:
                page.get_by_role(role, name=name).click()
            elif selector:
                page.click(selector)
            else:
                raise Exception("click: 대상 요소를 찾을 수 없습니다.")
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
    except Exception as e:
        outcome = "fail"
        error_msg = str(e)

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
    if action_result["outcome"] == "success":
        to_node = create_or_get_node(run_id, page)
        to_node_id = UUID(to_node["id"])

    if depth_diff_type is None and before_node:
        depth_diff_type = classify_change(before_node, to_node, page)

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
