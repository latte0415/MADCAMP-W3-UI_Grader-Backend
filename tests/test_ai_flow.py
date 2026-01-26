"""AI Flow 테스트 스크립트

입력값이 필요한 액션을 LLM으로 필터링하고 처리하는 전체 플로우를 테스트합니다.
"""
import os
import sys
import asyncio
import json
from pathlib import Path
from uuid import UUID
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from infra.supabase import get_client
from services.node_service import create_or_get_node
from services.edge_service import perform_and_record_edge
from services.ai_service import AiService
from utils.action_extractor import extract_actions_from_page, filter_input_required_actions
from schemas.actions import Action


def create_test_run(target_url: str, start_url: str) -> str:
    """테스트용 run 생성"""
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


async def test_ai_flow(info_existed: bool = False):
    """AI Flow 전체 플로우 테스트"""
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/signup")

    print("=" * 50)
    print("AI Flow 테스트 시작")
    print("=" * 50)

    try:
        # 1. 테스트 run 생성
        print("\n1. Run 생성 중...")
        run_id = create_test_run(target_url, start_url)
        print(f"   ✓ Run ID: {run_id}")

        if info_existed:
            from repositories.ai_memory_repository import create_run_memory
            create_run_memory(run_id, {
                "ID": "user1@test.com",
                "PW": "Test1234!"
            })

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(start_url, wait_until="networkidle")

            # 2. 노드 생성
            print("\n2. 노드 생성 중...")
            from_node = await create_or_get_node(UUID(run_id), page)
            from_node_id = UUID(from_node["id"])
            print(f"   ✓ from_node ID: {from_node_id}")

            # 3. 액션 추출
            print("\n3. 액션 추출 중...")
            all_actions = await extract_actions_from_page(page)
            print(f"   ✓ 전체 액션 수: {len(all_actions)}")

            # 4. 입력값 필요한 액션 필터링
            print("\n4. 입력값 필요한 액션 필터링 중...")
            input_actions = filter_input_required_actions(all_actions)
            print(f"   ✓ 입력 액션 수: {len(input_actions)}")
            
            if not input_actions:
                print("   ⚠ 입력 액션이 없습니다. 테스트를 종료합니다.")
                await browser.close()
                return

            # 입력 액션 정보 출력
            for idx, action in enumerate(input_actions, 1):
                print(f"   - 액션 {idx}: {action.get('action_type')} / {action.get('action_target')}")

            # 5. LLM 호출 (filter-action)
            print("\n5. LLM 호출 중 (filter-action)...")
            ai_service = AiService()
            
            # 액션을 딕셔너리 리스트로 변환 (JSON 직렬화 가능하도록)
            input_actions_dict = []
            for action in input_actions:
                action_dict = {
                    "action_type": action.get("action_type", ""),
                    "action_target": action.get("action_target", ""),
                    "action_value": action.get("action_value", ""),
                    "selector": action.get("selector", ""),
                    "role": action.get("role", ""),
                    "name": action.get("name", ""),
                    "tag": action.get("tag", ""),
                    "href": action.get("href", ""),
                    "input_type": action.get("input_type", ""),
                    "placeholder": action.get("placeholder", ""),
                    "input_required": action.get("input_required", False)
                }
                input_actions_dict.append(action_dict)
            
            filtered_actions = await ai_service.filter_input_actions_with_run_memory(
                input_actions=input_actions_dict,
                run_id=UUID(run_id),
                from_node_id=from_node_id
            )
            
            print(f"   ✓ 처리 가능한 액션 수: {len(filtered_actions)}")
            
            if not filtered_actions:
                print("   ⚠ 처리 가능한 액션이 없습니다. pending_action을 확인하세요.")
                await browser.close()
                return

            # 6. 처리 가능한 액션 실행 및 엣지 생성
            print("\n6. 액션 실행 및 엣지 생성 중...")
            for idx, action_dict in enumerate(filtered_actions, 1):
                print(f"\n   액션 {idx} 실행 중...")
                print(f"   - 타입: {action_dict.get('action_type')}")
                print(f"   - 타겟: {action_dict.get('action_target')}")
                print(f"   - 값: {action_dict.get('action_value', 'N/A')}")
                
                try:
                    # 액션 실행 및 엣지 기록
                    edge = await perform_and_record_edge(
                        run_id=UUID(run_id),
                        from_node_id=from_node_id,
                        page=page,
                        action=action_dict
                    )
                    
                    print(f"   ✓ 엣지 생성: {edge['id']}")
                    print(f"   ✓ 결과: {edge.get('outcome')}")
                    
                    if edge.get("to_node_id"):
                        print(f"   ✓ 도착 노드: {edge['to_node_id']}")
                    else:
                        print("   ⚠ 도착 노드 없음 (액션 실패 또는 상태 변화 없음)")
                    
                    if edge.get("error_msg"):
                        print(f"   ⚠ 에러: {edge['error_msg']}")
                        
                except Exception as e:
                    print(f"   ✗ 액션 실행 실패: {e}")
                    import traceback
                    traceback.print_exc()

            # 7. 도착 노드 생성 확인
            print("\n7. 도착 노드 확인 중...")
            # 마지막 엣지의 to_node_id 확인
            if filtered_actions:
                last_edge = await perform_and_record_edge(
                    run_id=UUID(run_id),
                    from_node_id=from_node_id,
                    page=page,
                    action=filtered_actions[-1]
                )
                if last_edge.get("to_node_id"):
                    to_node_id = last_edge["to_node_id"]
                    print(f"   ✓ 최종 도착 노드: {to_node_id}")
                else:
                    print("   ⚠ 도착 노드가 생성되지 않았습니다.")

            await browser.close()

        print("\n✓ 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_ai_flow())
    # asyncio.run(test_ai_flow(True))

