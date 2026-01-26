import os
import sys
from pathlib import Path
from uuid import UUID
from playwright.sync_api import sync_playwright

# 프로젝트 루트 경로 설정 (imports를 위해)
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from infra.supabase import get_client
from services.node_service import create_or_get_node
from services.edge_service import perform_and_record_edge
from utils.action_extractor import extract_actions_from_page

def create_test_run(target_url: str, start_url: str) -> str:
    supabase = get_client()
    run_data = {
        "target_url": target_url,
        "start_url": start_url,
        "status": "running",
        "metadata": {"test": True, "description": "Specific Button Click Test"}
    }
    result = supabase.table("runs").insert(run_data).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]["id"]
    raise Exception("Run 생성 실패")

def test_phase1_ambiguous_login_button():
    target_url = "http://localhost:5173/#phase1_analyze"
    start_url = "http://localhost:5173/#phase1_analyze"

    print("=" * 50)
    print(f"Test Start: Clicking 'Ambiguous Login' Button on {start_url}")
    print("=" * 50)

    try:
        # 1. Run 생성
        run_id = create_test_run(target_url, start_url)
        print(f"\n✓ Run Created: {run_id}")

        with sync_playwright() as p:
            # 2. 브라우저 실행
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            page = context.new_page()
            
            # 3. 페이지 이동
            print(f"✓ Navigating to {start_url}...")
            page.goto(start_url, wait_until="networkidle")

            # 4. 현재 상태 Node 생성/조회
            from_node = create_or_get_node(run_id, page)
            print(f"✓ Current Node ID: {from_node['id']}")

            # 5. 액션 추출
            actions = extract_actions_from_page(page)
            print(f"✓ Extracted {len(actions)} actions")

            # 6. 목표 버튼 찾기
            # <button class="action-btn" onclick="...">Go to 'Ambiguous Login' Page</button>
            target_text = "Go to 'Ambiguous Login' Page"
            target_action = None

            for action_item in actions:
                # 1. action_target 문자열 자체에 텍스트가 포함되어 있는지 확인 (가장 확실하고 빠름)
                # 예: "role=button name=Go to 'Ambiguous Login' Page"
                if target_text in action_item.get('action_target', ''):
                    target_action = action_item
                    break

                # 2. 텍스트나 HTML 등에서 식별 가능한지 확인 (이전 로직 fallback)
                try:
                    locator = page.locator(action_item['action_target'])
                    if locator.count() > 0:
                        text = locator.first.inner_text()
                        if target_text in text:
                            target_action = action_item
                            break
                except:
                    continue
            
            if not target_action:
                # 만약 text 매칭으로 못 찾았다면, action-btn 클래스로 찾아봄 (보완책)
                for action_item in actions:
                    if "action-btn" in action_item.get("html", "") and "Ambiguous Login" in action_item.get("html", ""):
                        target_action = action_item
                        break

            if not target_action:
                print(f"✗ Failed to find the button with text: {target_text}")
                print("Available actions:")
                for a in actions:
                    print(f" - {a.get('action_target')} | {a.get('action_type')}")
                return

            print(f"✓ Found Target Action: {target_action['action_target']}")

            # 7. 엣지 실행 및 기록
            edge = perform_and_record_edge(
                UUID(run_id),
                UUID(from_node["id"]),
                page,
                target_action
            )
            print(f"✓ Edge Recorded: {edge['id']}")
            
            if edge.get("to_node_id"):
                print(f"✓ Transitioned to Node: {edge['to_node_id']}")
            else:
                print("✓ No state change recorded (Self-loop or error)")

            browser.close()

        print("\n✓ Test Completed Successfully")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_phase1_ambiguous_login_button()
