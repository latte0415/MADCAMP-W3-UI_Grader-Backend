import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID
from playwright.async_api import async_playwright

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

async def test_phase2_depth_sequence():
    target_url = "http://localhost:5173/phase2_action"
    start_url = "http://localhost:5173/phase2_action"

    print("=" * 50)
    print(f"Test Start: Multi-step Sequence on {start_url}")
    print("=" * 50)

    try:
        # 1. Run 생성
        run_id = create_test_run(target_url, start_url)
        print(f"\n✓ Run Created: {run_id}")

        async with async_playwright() as p:
            # 2. 브라우저 실행
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            
            # 3. 페이지 이동
            print(f"✓ Navigating to {start_url}...")
            await page.goto(start_url, wait_until="networkidle")

            # Sequence of keywords to click
            keywords = [
                "다단계 작업 시작하기 (Depth 1)",
                "다음 단계로 (Depth 2) >",
                "다음 단계로 (Depth 3) >",
                "★ 목표물 클릭 (완료) ★"
            ]

            current_node_id = None

            for idx, search_keyword in enumerate(keywords, start=1):
                print(f"\n--- Step {idx}: Searching for '{search_keyword}' ---")
                
                # 4. 현재 상태 Node 생성/조회
                node = await create_or_get_node(run_id, page)
                current_node_id = node['id']
                print(f"✓ Current Node ID: {current_node_id}")

                # 5. 액션 추출
                actions = await extract_actions_from_page(page)
                print(f"✓ Extracted {len(actions)} actions")

                # 6. 목표 버튼 찾기
                target_action = None
                for action_item in actions:
                    is_match = False
                    
                    # 1. 메타데이터(target, html)에서 확인
                    metadata = (action_item.get('action_target', '') + action_item.get('html', '')).lower()
                    if search_keyword.lower() in metadata :
                        is_match = True
                    
                    # 2. 실제 텍스트 내용 확인 (메타데이터에 없을 경우)
                    if not is_match:
                        try:
                            # action_target is usually a selector or role string
                            # extract_actions_from_page might return something that locator can use
                            selector = action_item.get('action_target')
                            if selector:
                                locator = page.locator(selector)
                                if await locator.count() > 0:
                                    text = (await locator.first.inner_text()).lower()
                                    if search_keyword.lower() in text:
                                        is_match = True
                        except:
                            pass
                    
                    if is_match:
                        target_action = action_item
                        break

                if not target_action:
                    print(f"✗ Failed to find the button with text: {search_keyword}")
                    print("Available actions (first 5):")
                    for a in actions[:5]:
                        print(f" - {a.get('action_target')} | {a.get('text', '')}")
                    break

                print(f"✓ Found Target Action: {target_action['action_target']}")

                # 7. 엣지 실행 및 기록
                edge = await perform_and_record_edge(
                    UUID(run_id),
                    UUID(current_node_id),
                    page,
                    target_action
                )
                print(f"✓ Edge Recorded: {edge['id']}")
                print(f"✓ Outcome: {edge.get('outcome')}")
                print(f"✓ Current URL: {page.url}")
                
                # Wait a bit for navigation or animations
                await page.wait_for_timeout(500)

            await browser.close()

        print("\n✓ Multi-step sequence test completed")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_phase2_depth_sequence())

