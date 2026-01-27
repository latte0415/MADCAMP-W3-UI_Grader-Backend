"""엣지 액션 추출/기록 테스트 스크립트"""
import os
import random
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
    """테스트용 run 생성. Args: target_url, start_url. Returns: run_id (UUID 문자열)."""
    supabase = get_client()
    run_data = {
        "target_url": target_url,
        "start_url": start_url,
        "status": "running",
        "metadata": {"test": True}
    }
    result = supabase.table("runs").insert(run_data).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]["id"]
    raise Exception("Run 생성 실패")


async def test_edge_flow():
    target_url = os.getenv("TEST_TARGET_URL", "http://localhost:5173/#phase1_analyze")
    start_url = os.getenv("TEST_START_URL", "http://localhost:5173/#phase1_analyze")

    print("=" * 50)
    print("엣지 액션 추출/기록 테스트 시작")
    print("=" * 50)

    try:
        run_id = create_test_run(target_url, start_url)
        print(f"\n✓ Run 생성: {run_id}")
        print(f"  - Target: {target_url}")
        print(f"  - Start: {start_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(start_url, wait_until="networkidle")
            print(f"✓ 페이지 이동 완료: {page.url}")

            # from_node 생성
            from_node = await create_or_get_node(UUID(run_id), page)
            print(f"✓ from_node: {from_node['id']}")
            print(f"  - Node Hash: {from_node.get('node_hash')}")
            from_node_with_artifacts = get_node_with_artifacts(UUID(from_node["id"]))
            css_snapshot = None
            if from_node_with_artifacts and from_node_with_artifacts.get("artifacts"):
                css_snapshot = from_node_with_artifacts["artifacts"].get("css_snapshot")
            if css_snapshot:
                print(f"✓ CSS 스냅샷 로드됨 (length={len(css_snapshot)})")
            else:
                print("✗ CSS 스냅샷 로드 실패 또는 비어있음")

            # 액션 추출
            actions = await extract_actions_from_page(page)
            print(f"✓ 액션 추출 완료: {len(actions)}개 발견")
            if not actions:
                raise Exception("추출된 액션이 없습니다.")

            action = random.choice(actions)
            print(f"✓ 액션 선택: {action.get('action_type')} / {action.get('action_target')}")
            print(f"  - Selector: {action.get('xpath_selector') or action.get('css_selector')}")
            print(f"  - Description: {action.get('description')}")

            # 액션 수행 + 엣지 기록 (to_node 생성 포함)
            edge = await perform_and_record_edge(
                UUID(run_id),
                UUID(from_node["id"]),
                page,
                action
            )
            print(f"✓ 엣지 기록: {edge['id']}")
            print(f"✓ depth_diff_type: {edge.get('depth_diff_type')}")
            print(f"✓ Action ID: {edge.get('action_id')}")

            if edge.get("to_node_id"):
                print(f"✓ to_node 생성됨: {edge['to_node_id']}")
            else:
                print("✗ to_node 생성 실패 (액션 실패 또는 상태 변화 없음)")

            # 중복 테스트
            edge2 = await perform_and_record_edge(UUID(run_id), UUID(from_node["id"]), page, action)
            if edge["id"] == edge2["id"]:
                print(edge["id"])
                print(edge2["id"])
                print("✓ 중복 엣지 처리 OK")
            else:
                print("✗ 중복 엣지 처리 실패 (다른 ID)")

            await browser.close()

        print("\n✓ 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

async def test_three_actions_from_baseline():
    """기준점에서 액션 3개 실행 테스트"""
    target_url = os.getenv("TEST_TARGET_URL", "http://localhost:5173/#phase1_analyze")
    start_url = os.getenv("TEST_START_URL", "http://localhost:5173/#phase1_analyze")

    print("=" * 50)
    print("기준점에서 액션 3개 테스트 시작")
    print("=" * 50)

    try:
        run_id = create_test_run(target_url, start_url)
        print(f"\n✓ Run 생성: {run_id}")
        print(f"  - Target: {target_url}")
        print(f"  - Start: {start_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(start_url, wait_until="networkidle")
            print(f"✓ 페이지 이동 완료: {page.url}")

            from_node = await create_or_get_node(UUID(run_id), page)
            from_node_with_artifacts = get_node_with_artifacts(UUID(from_node["id"]))
            css_snapshot = None
            if from_node_with_artifacts and from_node_with_artifacts.get("artifacts"):
                css_snapshot = from_node_with_artifacts["artifacts"].get("css_snapshot")
            if css_snapshot:
                print(f"✓ CSS 스냅샷 로드됨 (length={len(css_snapshot)})")
            else:
                print("✗ CSS 스냅샷 로드 실패 또는 비어있음")
            actions = await extract_actions_from_page(page)
            print(f"✓ 액션 추출 완료: {len(actions)}개 발견")
            if len(actions) < 3:
                raise Exception("액션이 3개 미만입니다.")

            for idx, action in enumerate(random.sample(actions, 3), start=1):
                print(f"\n--- [Step {idx}] ---")
                print(f"선택된 액션: {action.get('action_type')} / {action.get('action_target')}")
                print(f"Selector: {action.get('xpath_selector') or action.get('css_selector')}")
                edge = await perform_and_record_edge(
                    UUID(run_id),
                    UUID(from_node["id"]),
                    page,
                    action
                )
                print(f"✓ 액션 {idx} 기록: {edge['id']}")

            await browser.close()

        print("\n✓ 테스트 완료")
        print("=" * 50)
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_two_step_sequence():
    """액션 2번 연속 수행 테스트"""
    target_url = os.getenv("TEST_TARGET_URL", "http://localhost:5173/#phase1_analyze")
    start_url = os.getenv("TEST_START_URL", "http://localhost:5173/#phase1_analyze")

    print("=" * 50)
    print("액션 2번 연속 테스트 시작")
    print("=" * 50)

    try:
        run_id = create_test_run(target_url, start_url)
        print(f"\n✓ Run 생성: {run_id}")
        print(f"  - Target: {target_url}")
        print(f"  - Start: {start_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(start_url, wait_until="networkidle")
            print(f"✓ 페이지 이동 완료: {page.url}")

            from_node = await create_or_get_node(UUID(run_id), page)
            from_node_with_artifacts = get_node_with_artifacts(UUID(from_node["id"]))
            css_snapshot = None
            if from_node_with_artifacts and from_node_with_artifacts.get("artifacts"):
                css_snapshot = from_node_with_artifacts["artifacts"].get("css_snapshot")
            if css_snapshot:
                print(f"✓ CSS 스냅샷 로드됨 (length={len(css_snapshot)})")
            else:
                print("✗ CSS 스냅샷 로드 실패 또는 비어있음")
            actions = await extract_actions_from_page(page)
            print(f"✓ 액션 추출 완료: {len(actions)}개 발견")
            if len(actions) < 2:
                raise Exception("액션이 2개 미만입니다.")

            # 랜덤하게 2개 선택
            selected_actions = random.sample(actions, 2)

            # 1st action
            edge1 = await perform_and_record_edge(
                UUID(run_id),
                UUID(from_node["id"]),
                page,
                selected_actions[0]
            )
            print(f"✓ 1차 액션 기록: {edge1['id']}")
            print(f"  - Action: {selected_actions[0].get('action_type')} / {selected_actions[0].get('action_target')}")
            print(f"  - To Node: {edge1.get('to_node_id')}")

            # 2nd action (현재 페이지 상태에서 계속)
            edge2 = await perform_and_record_edge(
                UUID(run_id),
                UUID(from_node["id"]),
                page,
                selected_actions[1]
            )
            print(f"✓ 2차 액션 기록: {edge2['id']}")
            print(f"  - Action: {selected_actions[1].get('action_type')} / {selected_actions[1].get('action_target')}")
            print(f"  - To Node: {edge2.get('to_node_id')}")

            await browser.close()

        print("\n✓ 테스트 완료")
        print("=" * 50)
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_edge_flow())