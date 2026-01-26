"""supabase.com 액션 테스트"""
import os
import sys
import asyncio
from pathlib import Path
from uuid import UUID
from playwright.async_api import async_playwright

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


async def test_action_list(url: str) -> None:
    """1) 액션 리스트 추출 (공통)"""
    print("=" * 50)
    print("액션 리스트 추출 테스트")
    print("=" * 50)

    try:
        run_id = create_test_run(url, url)
        print(f"✓ Run 생성: {run_id}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle")

            # 기준 노드 생성
            node = await create_or_get_node(UUID(run_id), page)
            print(f"✓ 기준 노드 생성: {node['id']}")
            node_with_artifacts = get_node_with_artifacts(UUID(node["id"]))
            css_snapshot = None
            if node_with_artifacts and node_with_artifacts.get("artifacts"):
                css_snapshot = node_with_artifacts["artifacts"].get("css_snapshot")
            if css_snapshot:
                print(f"✓ CSS 스냅샷 로드됨 (length={len(css_snapshot)})")
            else:
                print("✗ CSS 스냅샷 로드 실패 또는 비어있음")

            actions = await extract_actions_from_page(page)
            print(f"✓ 추출된 액션 수: {len(actions)}")

            # 전체 액션을 인덱스로 출력
            for idx, action in enumerate(actions):
                print(f"[{idx}] {action['action_type']}: {action['action_target']} (selector={action.get('selector')})")

            await browser.close()

        print("✓ 테스트 완료")
    except Exception as e:
        print(f"✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def _save_screenshot(page, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)


async def test_custom_flow(url: str) -> None:
    """2) 커스텀 플로우 테스트"""

    print("=" * 50)
    print(f"커스텀 플로우 테스트: {url}")
    print("=" * 50)

    try:
        run_id = create_test_run(url, url)
        print(f"✓ Run 생성: {run_id}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle")

            # 기준 노드 생성 (홈)
            home_node = await create_or_get_node(UUID(run_id), page)
            print(f"✓ home_node: {home_node['id']}")
            home_node_with_artifacts = get_node_with_artifacts(UUID(home_node["id"]))
            home_css_snapshot = None
            if home_node_with_artifacts and home_node_with_artifacts.get("artifacts"):
                home_css_snapshot = home_node_with_artifacts["artifacts"].get("css_snapshot")
            if home_css_snapshot:
                print(f"✓ CSS 스냅샷 로드됨 (length={len(home_css_snapshot)})")
            else:
                print("✗ CSS 스냅샷 로드 실패 또는 비어있음")

            # 첫 번째 액션 (액션 리스트에서 번호 입력으로 선택)
            actions = await extract_actions_from_page(page)
            if not actions:
                raise Exception("추출된 액션이 없습니다.")

            action1_input = input("첫 번째 액션 인덱스 입력 (기본값 0): ").strip()
            if not action1_input:
                action1_input = os.getenv("ACTION1_INDEX", "0")
            action1_idx = int(action1_input)
            if action1_idx < 0 or action1_idx >= len(actions):
                raise Exception(f"ACTION1_INDEX 범위 오류: {action1_idx}")
            action1 = actions[action1_idx]
            print(f"✓ action1 선택: {action1['action_target']} (idx={action1_idx})")
            print(f"  action1 detail: type={action1['action_type']} role={action1.get('role')} name={action1.get('name')} selector={action1.get('selector')}")
            await _save_screenshot(page, Path("artifacts") / "custom_flow" / "action1_before.png")
            edge1 = await perform_and_record_edge(UUID(run_id), UUID(home_node["id"]), page, action1)
            await _save_screenshot(page, Path("artifacts") / "custom_flow" / "action1_after.png")
            print(f"✓ action1 edge: {edge1['id']} (depth_diff_type={edge1.get('depth_diff_type')})")

            action1_node = await create_or_get_node(UUID(run_id), page)
            print(f"✓ action1_node: {action1_node['id']}")

            # 두 번째 액션 (액션 리스트에서 번호 입력으로 선택)
            action2_list = await extract_actions_from_page(page)
            if not action2_list:
                raise Exception("추출된 액션이 없습니다. (action2)")

            action2_input = input("두 번째 액션 인덱스 입력 (기본값 0): ").strip()
            if not action2_input:
                action2_input = os.getenv("ACTION2_INDEX", "0")
            action2_idx = int(action2_input)
            if action2_idx < 0 or action2_idx >= len(action2_list):
                raise Exception(f"ACTION2_INDEX 범위 오류: {action2_idx}")
            action2 = action2_list[action2_idx]
            print(f"✓ action2 선택: {action2['action_target']} (idx={action2_idx})")
            print(f"  action2 detail: type={action2['action_type']} role={action2.get('role')} name={action2.get('name')} selector={action2.get('selector')}")
            await _save_screenshot(page, Path("artifacts") / "custom_flow" / "action2_before.png")
            edge2 = await perform_and_record_edge(UUID(run_id), UUID(action1_node["id"]), page, action2)
            await _save_screenshot(page, Path("artifacts") / "custom_flow" / "action2_after.png")
            print(f"✓ action2 edge: {edge2['id']} (depth_diff_type={edge2.get('depth_diff_type')})")

            action2_node = await create_or_get_node(UUID(run_id), page)
            print(f"✓ action2_node: {action2_node['id']}")

            await browser.close()

        print("✓ 테스트 완료")
    except Exception as e:
        print(f"✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # 1) 액션 리스트 추출 (공통)
    asyncio.run(test_action_list(os.getenv("TEST_ACTION_LIST_URL", "https://urround.com/")))
    # 2) 커스텀 플로우 테스트
    asyncio.run(test_custom_flow(os.getenv("TEST_ACTION_LIST_URL", "https://urround.com/")))
