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

            # 2. 초기 노드 생성
            print("\n2. 초기 노드 생성 중...")
            current_node = await create_or_get_node(UUID(run_id), page)
            current_node_id = UUID(current_node["id"])
            print(f"   ✓ 초기 노드 ID: {current_node_id}")

            # 3. DFS 방식으로 연쇄적 이동 (3번 반복)
            print("\n3. DFS 방식 연쇄적 이동 시작 (3번 반복)...")
            ai_service = AiService()
            
            for step in range(1, 4):  # 3번 반복
                print(f"\n{'='*50}")
                print(f"Step {step}/3")
                print(f"{'='*50}")
                
                # 3-1. 현재 노드에서 액션 추출
                print(f"\n[{step}] 액션 추출 중...")
                all_actions = await extract_actions_from_page(page)
                print(f"   ✓ 전체 액션 수: {len(all_actions)}")
                
                if not all_actions:
                    print("   ⚠ 액션이 없습니다. 이동을 종료합니다.")
                    break
                
                # 3-2. 입력값 필요한 액션 필터링
                print(f"\n[{step}] 입력값 필요한 액션 필터링 중...")
                input_actions = filter_input_required_actions(all_actions)
                print(f"   ✓ 입력 액션 수: {len(input_actions)}")
                
                # 입력 액션이 없으면 일반 액션 중 첫 번째 사용
                if not input_actions:
                    print("   ⚠ 입력 액션이 없습니다. 일반 액션 사용...")
                    if all_actions:
                        selected_action = all_actions[0]
                        print(f"   ✓ 선택된 액션: {selected_action.get('action_type')} / {selected_action.get('action_target')}")
                        
                        # 일반 액션 실행
                        try:
                            edge = await perform_and_record_edge(
                                run_id=UUID(run_id),
                                from_node_id=current_node_id,
                                page=page,
                                action=selected_action
                            )
                            
                            print(f"   ✓ 엣지 생성: {edge['id']}")
                            print(f"   ✓ 결과: {edge.get('outcome')}")
                            
                            if edge.get("to_node_id"):
                                current_node_id = UUID(edge["to_node_id"])
                                print(f"   ✓ 다음 노드로 이동: {current_node_id}")
                            else:
                                print("   ⚠ 도착 노드 없음 (액션 실패 또는 상태 변화 없음)")
                                break
                            
                            if edge.get("error_msg"):
                                print(f"   ⚠ 에러: {edge['error_msg']}")
                                break
                        except Exception as e:
                            print(f"   ✗ 액션 실행 실패: {e}")
                            import traceback
                            traceback.print_exc()
                            break
                    else:
                        print("   ⚠ 사용 가능한 액션이 없습니다.")
                        break
                    continue
                
                # 입력 액션 정보 출력
                for idx, action in enumerate(input_actions, 1):
                    print(f"   - 입력 액션 {idx}: {action.get('action_type')} / {action.get('action_target')}")
                
                # 3-3. 현재 입력 필드 값 수집 (이미 채워진 필드 확인용)
                from utils.state_collector import collect_input_values
                current_input_values = await collect_input_values(page)
                
                # 디버깅: 수집된 입력 필드 값 출력
                if current_input_values:
                    print(f"   [디버깅] 현재 입력 필드 값 수집됨: {len(current_input_values)}개")
                    for key, value in current_input_values.items():
                        print(f"      - {key}: {value[:30]}...")
                else:
                    print(f"   [디버깅] 현재 입력 필드 값 없음")
                
                # 디버깅: 입력 액션의 action_target 출력
                print(f"   [디버깅] 입력 액션 action_target 목록:")
                for action in input_actions:
                    print(f"      - {action.get('action_target')} (role={action.get('role')}, name={action.get('name')})")
                
                # 3-4. LLM 호출 (filter-action)
                print(f"\n[{step}] LLM 호출 중 (filter-action)...")
                
                # 액션을 딕셔너리 리스트로 변환 (현재 값 정보 포함)
                input_actions_dict = []
                for action in input_actions:
                    action_target = action.get("action_target", "")
                    role = action.get("role", "")
                    name = action.get("name", "")
                    selector = action.get("selector", "")
                    
                    # 현재 입력 필드에 값이 있는지 확인
                    is_filled = False
                    current_value = ""
                    
                    # action_target으로 매칭 시도 (가장 정확)
                    if action_target in current_input_values:
                        is_filled = True
                        current_value = current_input_values[action_target]
                        print(f"   [매칭] action_target으로 매칭: '{action_target}' = '{current_value[:30]}...'")
                    # role + name으로 매칭 시도
                    elif role and name:
                        key = f"role={role} name={name}"
                        if key in current_input_values:
                            is_filled = True
                            current_value = current_input_values[key]
                            print(f"   [매칭] role+name으로 매칭: '{key}' = '{current_value[:30]}...'")
                    # selector로 매칭 시도
                    elif selector and selector in current_input_values:
                        is_filled = True
                        current_value = current_input_values[selector]
                        print(f"   [매칭] selector로 매칭: '{selector}' = '{current_value[:30]}...'")
                    else:
                        # 매칭 실패 시 디버깅 정보 출력
                        print(f"   [매칭 실패] action_target='{action_target}', role='{role}', name='{name}', selector='{selector}'")
                        print(f"   [매칭 실패] 수집된 키 목록: {list(current_input_values.keys())}")
                    
                    action_dict = {
                        "action_type": action.get("action_type", ""),
                        "action_target": action_target,
                        "action_value": action.get("action_value", ""),
                        "selector": selector,
                        "role": role,
                        "name": name,
                        "tag": action.get("tag", ""),
                        "href": action.get("href", ""),
                        "input_type": action.get("input_type", ""),
                        "placeholder": action.get("placeholder", ""),
                        "input_required": action.get("input_required", False),
                        "is_filled": is_filled,  # 이미 값이 채워져 있는지
                        "current_value": current_value if is_filled else ""  # 현재 값 (있는 경우만)
                    }
                    input_actions_dict.append(action_dict)
                    
                    if is_filled:
                        print(f"   ⚠ 액션 '{action_target}'은(는) 이미 값이 채워져 있습니다: '{current_value[:50]}'")
                
                filtered_actions = await ai_service.filter_input_actions_with_run_memory(
                    input_actions=input_actions_dict,
                    run_id=UUID(run_id),
                    from_node_id=current_node_id
                )
                
                print(f"   ✓ 처리 가능한 액션 수: {len(filtered_actions)}")
                
                if not filtered_actions:
                    print("   ⚠ 처리 가능한 액션이 없습니다. pending_action을 확인하세요.")
                    break
                
                # 3-4. 첫 번째 액션만 실행 (DFS 방식)
                action_dict = filtered_actions[0]
                print(f"\n[{step}] 액션 실행 중...")
                print(f"   - 타입: {action_dict.get('action_type')}")
                print(f"   - 타겟: {action_dict.get('action_target')}")
                print(f"   - 값: {action_dict.get('action_value', 'N/A')}")
                print(f"   - role: {action_dict.get('role')}")
                print(f"   - name: {action_dict.get('name')}")
                print(f"   - selector: {action_dict.get('selector')}")
                print(f"   [디버깅] 전체 액션 딕셔너리: {action_dict}")
                
                try:
                    # 액션 실행 전 중복 검증
                    from services.edge_service import is_duplicate_action
                    existing_edge = is_duplicate_action(
                        run_id=UUID(run_id),
                        from_node_id=current_node_id,
                        action=action_dict
                    )
                    
                    if existing_edge:
                        print(f"   ⚠ 중복 액션 발견: 이미 실행된 엣지 {existing_edge['id']}")
                        if existing_edge.get("to_node_id"):
                            current_node_id = UUID(existing_edge["to_node_id"])
                            print(f"   ✓ 기존 엣지의 도착 노드로 이동: {current_node_id}")
                        else:
                            print("   ⚠ 기존 엣지에 도착 노드가 없습니다. 다음 단계로 진행합니다.")
                        continue
                    
                    # 액션 실행 및 엣지 기록
                    edge = await perform_and_record_edge(
                        run_id=UUID(run_id),
                        from_node_id=current_node_id,
                        page=page,
                        action=action_dict
                    )
                    
                    print(f"   ✓ 엣지 생성: {edge['id']}")
                    print(f"   ✓ 결과: {edge.get('outcome')}")
                    
                    if edge.get("to_node_id"):
                        current_node_id = UUID(edge["to_node_id"])
                        print(f"   ✓ 다음 노드로 이동: {current_node_id}")
                    else:
                        print("   ⚠ 도착 노드 없음 (액션 실패 또는 상태 변화 없음)")
                        break
                    
                    if edge.get("error_msg"):
                        print(f"   ⚠ 에러: {edge['error_msg']}")
                        break
                        
                except Exception as e:
                    print(f"   ✗ 액션 실행 실패: {e}")
                    import traceback
                    traceback.print_exc()
                    break

            await browser.close()

        print("\n✓ 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # asyncio.run(test_ai_flow())
    asyncio.run(test_ai_flow(True))

