"""supabase.com 액션 테스트"""
import os
import sys
from pathlib import Path
from uuid import UUID
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from infra.supabase import get_client
from services.node_service import create_or_get_node, get_node_with_artifacts
from services.edge_service import perform_and_record_edge
from utils.action_extractor import extract_actions_from_page


def create_test_run(target_url: str, start_url: str) -> str:
    supabase = get_client()
    run_data = {
        "target_url": target_url,
        "start_url": start_url,
        "status": "running",
        "metadata": {"test": True, "site": "supabase.com"}
    }
    result = supabase.table("runs").insert(run_data).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]["id"]
    raise Exception("Run 생성 실패")


def test_action_list(url: str) -> None:
    """1) 액션 리스트 추출 (공통)"""
    print("=" * 50)
    print("액션 리스트 추출 테스트")
    print("=" * 50)

    try:
        run_id = create_test_run(url, url)
        print(f"✓ Run 생성: {run_id}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle")

            # 기준 노드 생성
            node = create_or_get_node(run_id, page)
            print(f"✓ 기준 노드 생성: {node['id']}")
            node_with_artifacts = get_node_with_artifacts(node["id"])
            css_snapshot = None
            if node_with_artifacts and node_with_artifacts.get("artifacts"):
                css_snapshot = node_with_artifacts["artifacts"].get("css_snapshot")
            if css_snapshot:
                print(f"✓ CSS 스냅샷 로드됨 (length={len(css_snapshot)})")
            else:
                print("✗ CSS 스냅샷 로드 실패 또는 비어있음")

            actions = extract_actions_from_page(page)
            print(f"✓ 추출된 액션 수: {len(actions)}")

            # 전체 액션을 인덱스로 출력
            for idx, action in enumerate(actions):
                print(f"[{idx}] {action['action_type']}: {action['action_target']} (selector={action.get('selector')})")

            browser.close()

        print("✓ 테스트 완료")
    except Exception as e:
        print(f"✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_pricing_then_logo() -> None:
    """2) pricing 클릭 → Open main menu 클릭"""
    url = "https://supabase.com"

    print("=" * 50)
    print("pricing → Open main menu 클릭 테스트")
    print("=" * 50)

    try:
        run_id = create_test_run(url, url)
        print(f"✓ Run 생성: {run_id}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle")

            # 기준 노드 생성 (홈)
            home_node = create_or_get_node(run_id, page)
            print(f"✓ home_node: {home_node['id']}")
            home_node_with_artifacts = get_node_with_artifacts(home_node["id"])
            home_css_snapshot = None
            if home_node_with_artifacts and home_node_with_artifacts.get("artifacts"):
                home_css_snapshot = home_node_with_artifacts["artifacts"].get("css_snapshot")
            if home_css_snapshot:
                print(f"✓ CSS 스냅샷 로드됨 (length={len(home_css_snapshot)})")
            else:
                print("✗ CSS 스냅샷 로드 실패 또는 비어있음")

            # pricing 클릭 (액션 리스트에서 선택)
            actions = extract_actions_from_page(page)
            if not actions:
                raise Exception("추출된 액션이 없습니다.")

            pricing_idx = int(os.getenv("PRICING_ACTION_INDEX", "0"))
            if pricing_idx < 0 or pricing_idx >= len(actions):
                raise Exception(f"PRICING_ACTION_INDEX 범위 오류: {pricing_idx}")
            pricing_action = actions[pricing_idx]
            print(f"✓ pricing_action 선택: {pricing_action['action_target']} (idx={pricing_idx})")
            edge1 = perform_and_record_edge(UUID(run_id), UUID(home_node["id"]), page, pricing_action)
            print(f"✓ pricing edge: {edge1['id']} (depth_diff_type={edge1.get('depth_diff_type')})")

            pricing_node = create_or_get_node(run_id, page)
            print(f"✓ pricing_node: {pricing_node['id']}")

            # Open main menu 클릭
            menu_action = {
                "action_type": "click",
                "role": "button",
                "name": "Open main menu",
                "selector": "button[aria-label='Open main menu'], button[aria-expanded]",
                "action_target": "role=button name=Open main menu",
                "action_value": ""
            }
            edge2 = perform_and_record_edge(UUID(run_id), UUID(pricing_node["id"]), page, menu_action)
            print(f"✓ menu edge: {edge2['id']} (depth_diff_type={edge2.get('depth_diff_type')})")

            menu_node = create_or_get_node(run_id, page)
            print(f"✓ menu_node: {menu_node['id']}")

            browser.close()

        print("✓ 테스트 완료")
    except Exception as e:
        print(f"✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # 1) 액션 리스트 추출 (공통)
    test_action_list(os.getenv("TEST_ACTION_LIST_URL", "https://supabase.com"))
    # 2) pricing → logo
    # test_pricing_then_logo()
