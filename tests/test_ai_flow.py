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
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from infra.supabase import get_client
from services.node_service import create_or_get_node
from services.edge_service import perform_and_record_edge
from services.ai_service import AiService
from services.pending_action_service import PendingActionService
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


async def test_interactive_action_selection(info_existed: bool = False):
    """
    LLM 처리 이후 처리 가능한 액션 리스트를 보여주고, 사용자가 선택한 액션을 실행합니다.
    
    - 기존 입력 없이 가능한 액션 (일반 액션)
    - 입력이 생겨서 가능한 액션 (LLM이 처리 가능하다고 판단한 액션)
    - pending action에서 처리 가능해진 액션
    """
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/signup")

    print("=" * 50)
    print("Interactive Action Selection 테스트 시작")
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
            browser = await p.chromium.launch(headless=False)  # 상호작용을 위해 headless=False
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

            ai_service = AiService()
            pending_action_service = PendingActionService()
            
            while True:
                print(f"\n{'='*50}")
                print("액션 수집 및 선택")
                print(f"{'='*50}")
                
                # 3. 현재 노드에서 액션 추출
                print("\n[1] 액션 추출 중...")
                all_actions = await extract_actions_from_page(page)
                print(f"   ✓ 전체 액션 수: {len(all_actions)}")
                
                if not all_actions:
                    print("   ⚠ 액션이 없습니다. 종료합니다.")
                    break
                
                # 4. 입력값 필요한 액션과 일반 액션 분리
                print("\n[2] 액션 분류 중...")
                input_actions = filter_input_required_actions(all_actions)
                normal_actions = [a for a in all_actions if a not in input_actions]
                
                print(f"   ✓ 일반 액션 수: {len(normal_actions)}")
                print(f"   ✓ 입력 액션 수: {len(input_actions)}")
                
                # 5. 입력 액션 처리 (LLM 필터링)
                filtered_actions = []
                if input_actions:
                    print("\n[3] LLM으로 입력 액션 필터링 중...")
                    
                    # 현재 입력 필드 값 수집
                    from utils.state_collector import collect_input_values
                    current_input_values = await collect_input_values(page)
                    
                    # 입력 액션을 딕셔너리로 변환
                    input_actions_dict = []
                    for action in input_actions:
                        action_target = action.get("action_target", "")
                        role = action.get("role", "")
                        name = action.get("name", "")
                        selector = action.get("selector", "")
                        
                        # 현재 입력 필드에 값이 있는지 확인
                        is_filled = False
                        current_value = ""
                        
                        if action_target in current_input_values:
                            is_filled = True
                            current_value = current_input_values[action_target]
                        elif role and name:
                            key = f"role={role} name={name}"
                            if key in current_input_values:
                                is_filled = True
                                current_value = current_input_values[key]
                        elif selector and selector in current_input_values:
                            is_filled = True
                            current_value = current_input_values[selector]
                        
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
                            "is_filled": is_filled,
                            "current_value": current_value if is_filled else ""
                        }
                        input_actions_dict.append(action_dict)
                    
                    filtered_actions = await ai_service.filter_input_actions_with_run_memory(
                        input_actions=input_actions_dict,
                        run_id=UUID(run_id),
                        from_node_id=current_node_id
                    )
                    print(f"   ✓ LLM 처리 가능한 액션 수: {len(filtered_actions)}")
                
                # 6. Pending action 조회 및 처리 가능한지 확인
                print("\n[4] Pending action 조회 중...")
                pending_actions = pending_action_service.list_pending_actions(
                    run_id=UUID(run_id),
                    from_node_id=current_node_id,
                    status="pending"
                )
                print(f"   ✓ Pending action 수: {len(pending_actions)}")
                
                # Pending action을 다시 필터링하여 처리 가능한지 확인
                processable_pending_actions = []
                if pending_actions:
                    # Pending action을 input_actions 형태로 변환
                    pending_input_actions = []
                    for pending in pending_actions:
                        pending_dict = {
                            "action_type": pending.get("action_type", ""),
                            "action_target": pending.get("action_target", ""),
                            "action_value": pending.get("action_value", ""),
                            "selector": "",
                            "role": "",
                            "name": "",
                            "tag": "",
                            "href": "",
                            "input_type": "",
                            "placeholder": "",
                            "input_required": True,
                            "is_filled": False,
                            "current_value": ""
                        }
                        pending_input_actions.append(pending_dict)
                    
                    # LLM으로 다시 필터링
                    if pending_input_actions:
                        processable_pending_actions = await ai_service.filter_input_actions_with_run_memory(
                            input_actions=pending_input_actions,
                            run_id=UUID(run_id),
                            from_node_id=current_node_id
                        )
                        print(f"   ✓ Pending에서 처리 가능한 액션 수: {len(processable_pending_actions)}")
                
                # 7. 모든 가능한 액션 리스트 구성 및 표시
                print("\n" + "="*50)
                print("처리 가능한 액션 리스트")
                print("="*50)
                
                available_actions = []
                action_index = 1
                
                # 일반 액션 (입력 없이 가능)
                if normal_actions:
                    print(f"\n[일반 액션] (입력 없이 가능)")
                    for action in normal_actions:
                        print(f"  {action_index}. [{action.get('action_type')}] {action.get('action_target')}")
                        available_actions.append({
                            "action": action,
                            "type": "normal",
                            "source": "일반 액션"
                        })
                        action_index += 1
                
                # LLM 처리 가능한 액션
                if filtered_actions:
                    print(f"\n[LLM 처리 가능한 액션] (입력값 생성됨)")
                    for action in filtered_actions:
                        action_type = action.get('action_type', '')
                        action_target = action.get('action_target', '')
                        action_value = action.get('action_value', 'N/A')
                        print(f"  {action_index}. [{action_type}] {action_target}")
                        print(f"      값: {action_value[:50]}{'...' if len(str(action_value)) > 50 else ''}")
                        available_actions.append({
                            "action": action,
                            "type": "filtered",
                            "source": "LLM 처리"
                        })
                        action_index += 1
                
                # Pending에서 처리 가능한 액션
                if processable_pending_actions:
                    print(f"\n[Pending에서 처리 가능한 액션] (이전에 불가능했지만 이제 가능)")
                    for action in processable_pending_actions:
                        action_type = action.get('action_type', '')
                        action_target = action.get('action_target', '')
                        action_value = action.get('action_value', 'N/A')
                        print(f"  {action_index}. [{action_type}] {action_target}")
                        print(f"      값: {action_value[:50]}{'...' if len(str(action_value)) > 50 else ''}")
                        available_actions.append({
                            "action": action,
                            "type": "pending",
                            "source": "Pending 처리"
                        })
                        action_index += 1
                
                if not available_actions:
                    print("\n   ⚠ 처리 가능한 액션이 없습니다.")
                    break
                
                # 8. 사용자 입력 받기
                print("\n" + "="*50)
                try:
                    choice = input(f"\n실행할 액션 번호를 선택하세요 (1-{len(available_actions)}, 0=종료): ").strip()
                    
                    if choice == "0":
                        print("종료합니다.")
                        break
                    
                    choice_num = int(choice)
                    if choice_num < 1 or choice_num > len(available_actions):
                        print(f"   ✗ 잘못된 번호입니다. 1-{len(available_actions)} 사이의 숫자를 입력하세요.")
                        continue
                    
                    selected = available_actions[choice_num - 1]
                    selected_action = selected["action"]
                    
                    print(f"\n선택된 액션: [{selected['source']}] {selected_action.get('action_type')} / {selected_action.get('action_target')}")
                    if selected_action.get('action_value'):
                        print(f"  값: {selected_action.get('action_value')}")
                    
                    # 9. 액션 실행
                    print("\n[5] 액션 실행 중...")
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
                        
                        if edge.get("error_msg"):
                            print(f"   ⚠ 에러: {edge['error_msg']}")
                            
                    except Exception as e:
                        print(f"   ✗ 액션 실행 실패: {e}")
                        import traceback
                        traceback.print_exc()
                        
                except ValueError:
                    print("   ✗ 숫자를 입력해주세요.")
                except KeyboardInterrupt:
                    print("\n종료합니다.")
                    break
                except Exception as e:
                    print(f"   ✗ 오류: {e}")
                    import traceback
                    traceback.print_exc()

            await browser.close()

        print("\n✓ 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_process_pending_actions():
    """process_pending_actions_with_run_memory 메서드 테스트"""
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/signup")

    print("=" * 50)
    print("Process Pending Actions 테스트 시작")
    print("=" * 50)

    try:
        # 1. 테스트 run 생성
        print("\n1. Run 생성 중...")
        run_id = create_test_run(target_url, start_url)
        print(f"   ✓ Run ID: {run_id}")

        # 2. run_memory 설정
        print("\n2. Run Memory 설정 중...")
        from repositories.ai_memory_repository import create_run_memory
        run_memory_content = {
            "ID": "user1@test.com",
            "PW": "Test1234!"
        }
        create_run_memory(UUID(run_id), run_memory_content)
        print(f"   ✓ Run Memory 설정 완료: {run_memory_content}")

        # 3. 테스트용 노드 생성 (간단한 방법)
        print("\n3. 테스트용 노드 생성 중...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(start_url, wait_until="networkidle")

            current_node = await create_or_get_node(UUID(run_id), page)
            current_node_id = UUID(current_node["id"])
            print(f"   ✓ 노드 ID: {current_node_id}")

            await browser.close()

        # 4. Pending Actions 생성
        print("\n4. Pending Actions 생성 중...")
        pending_action_service = PendingActionService()
        
        # run_memory로 채울 수 있는 액션들
        pending_action1 = pending_action_service.create_pending_action(
            run_id=UUID(run_id),
            from_node_id=current_node_id,
            action={
                "action_type": "fill",
                "action_target": "role=textbox name=이메일 또는 사용자 ID",
                "action_value": "",
                "input_required": True
            },
            status="pending"
        )
        print(f"   ✓ Pending Action 1 생성: {pending_action1.get('action_target')}")

        pending_action2 = pending_action_service.create_pending_action(
            run_id=UUID(run_id),
            from_node_id=current_node_id,
            action={
                "action_type": "fill",
                "action_target": "role=textbox name=비밀번호",
                "action_value": "",
                "input_required": True
            },
            status="pending"
        )
        print(f"   ✓ Pending Action 2 생성: {pending_action2.get('action_target')}")

        # run_memory로 채울 수 없는 액션 (주소 입력 등)
        pending_action3 = pending_action_service.create_pending_action(
            run_id=UUID(run_id),
            from_node_id=current_node_id,
            action={
                "action_type": "fill",
                "action_target": "role=textbox name=주소",
                "action_value": "",
                "input_required": True
            },
            status="pending"
        )
        print(f"   ✓ Pending Action 3 생성: {pending_action3.get('action_target')}")

        # 5. 메서드 실행 전 상태 확인
        print("\n5. 메서드 실행 전 상태 확인...")
        before_pending_actions = pending_action_service.list_pending_actions(
            run_id=UUID(run_id),
            from_node_id=None,
            status="pending"
        )
        print(f"   ✓ Pending Actions 수: {len(before_pending_actions)}")
        for i, pending in enumerate(before_pending_actions, 1):
            print(f"      {i}. [{pending.get('action_type')}] {pending.get('action_target')}")

        # 6. 메서드 실행
        print("\n6. process_pending_actions_with_run_memory 실행 중...")
        ai_service = AiService()
        processable_actions = await ai_service.process_pending_actions_with_run_memory(
            run_id=UUID(run_id)
        )
        print(f"   ✓ 처리 가능한 액션 수: {len(processable_actions)}")

        # 7. 결과 검증 및 출력
        print("\n7. 결과 검증...")
        
        # 7.1 처리 가능한 액션 출력
        if processable_actions:
            print("\n   [처리 가능한 액션 리스트]")
            for i, action in enumerate(processable_actions, 1):
                action_type = action.get('action_type', '')
                action_target = action.get('action_target', '')
                action_value = action.get('action_value', 'N/A')
                print(f"      {i}. [{action_type}] {action_target}")
                print(f"         값: {action_value[:50]}{'...' if len(str(action_value)) > 50 else ''}")
                
                # action_value가 채워져 있는지 확인
                if not action_value or action_value == "":
                    print(f"         ⚠ 경고: action_value가 비어있습니다!")
                else:
                    print(f"         ✓ action_value가 채워져 있습니다")
        else:
            print("   ⚠ 처리 가능한 액션이 없습니다.")

        # 7.2 삭제 확인
        after_pending_actions = pending_action_service.list_pending_actions(
            run_id=UUID(run_id),
            from_node_id=None,
            status="pending"
        )
        deleted_count = len(before_pending_actions) - len(after_pending_actions)
        print(f"\n   ✓ 삭제된 Pending Actions 수: {deleted_count}")
        print(f"   ✓ 남아있는 Pending Actions 수: {len(after_pending_actions)}")

        if after_pending_actions:
            print("\n   [남아있는 Pending Actions]")
            for i, pending in enumerate(after_pending_actions, 1):
                print(f"      {i}. [{pending.get('action_type')}] {pending.get('action_target')}")

        # 7.3 검증
        print("\n8. 검증 결과...")
        success = True
        
        # 처리 가능한 액션이 2개여야 함 (ID, PW)
        if len(processable_actions) != 2:
            print(f"   ✗ 처리 가능한 액션 수가 예상과 다릅니다. 예상: 2, 실제: {len(processable_actions)}")
            success = False
        else:
            print(f"   ✓ 처리 가능한 액션 수가 예상과 일치합니다: {len(processable_actions)}")

        # 모든 처리 가능한 액션에 action_value가 채워져 있어야 함
        for action in processable_actions:
            if not action.get('action_value') or action.get('action_value') == "":
                print(f"   ✗ action_value가 비어있는 액션이 있습니다: {action.get('action_target')}")
                success = False
        if success:
            print("   ✓ 모든 처리 가능한 액션에 action_value가 채워져 있습니다.")

        # 삭제된 pending actions 수 확인
        if deleted_count != 2:
            print(f"   ✗ 삭제된 Pending Actions 수가 예상과 다릅니다. 예상: 2, 실제: {deleted_count}")
            success = False
        else:
            print(f"   ✓ 삭제된 Pending Actions 수가 예상과 일치합니다: {deleted_count}")

        # 남아있는 pending action이 1개여야 함 (주소)
        if len(after_pending_actions) != 1:
            print(f"   ✗ 남아있는 Pending Actions 수가 예상과 다릅니다. 예상: 1, 실제: {len(after_pending_actions)}")
            success = False
        else:
            print(f"   ✓ 남아있는 Pending Actions 수가 예상과 일치합니다: {len(after_pending_actions)}")

        if success:
            print("\n✓ 모든 검증 통과!")
        else:
            print("\n✗ 일부 검증 실패")

        print("\n✓ 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def wait_for_intent_label(edge_id: UUID, max_wait_seconds: int = 30) -> Optional[str]:
    """
    엣지의 intent_label이 생성될 때까지 polling으로 대기합니다.
    
    Args:
        edge_id: 엣지 ID
        max_wait_seconds: 최대 대기 시간 (초)
    
    Returns:
        intent_label 문자열 또는 None (타임아웃 시)
    """
    from repositories.edge_repository import get_edge_by_id
    import time
    
    start_time = time.time()
    check_interval = 0.5  # 0.5초마다 확인
    
    while time.time() - start_time < max_wait_seconds:
        edge = get_edge_by_id(edge_id)
        if edge and edge.get("intent_label"):
            return edge.get("intent_label")
        await asyncio.sleep(check_interval)
    
    return None


async def test_guess_edge_intent():
    """guess_and_update_edge_intent 메서드 테스트
    
    - run_memory를 미리 설정
    - input 액션부터 순서대로 3개 실행
    - 각 엣지의 intent_label 생성 완료까지 대기
    """
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/signup")

    print("=" * 50)
    print("Guess Edge Intent 테스트 시작")
    print("=" * 50)

    try:
        # 1. 테스트 run 생성
        print("\n1. Run 생성 중...")
        run_id = create_test_run(target_url, start_url)
        print(f"   ✓ Run ID: {run_id}")

        # 2. run_memory 설정
        print("\n2. Run Memory 설정 중...")
        from repositories.ai_memory_repository import create_run_memory
        run_memory_content = {
            "ID": "user1@test.com",
            "PW": "Test1234!"
        }
        create_run_memory(UUID(run_id), run_memory_content)
        print(f"   ✓ Run Memory 설정 완료: {run_memory_content}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(start_url, wait_until="networkidle")

            # 3. 초기 노드 생성
            print("\n3. 초기 노드 생성 중...")
            current_node = await create_or_get_node(UUID(run_id), page)
            current_node_id = UUID(current_node["id"])
            print(f"   ✓ 초기 노드 ID: {current_node_id}")

            # 4. AI Service 초기화
            ai_service = AiService()
            
            # 5. input 액션부터 순서대로 3개 실행
            print("\n4. Input 액션 순서대로 실행 시작 (3개)...")
            created_edges = []
            
            for step in range(1, 4):  # 3번 반복
                print(f"\n{'='*50}")
                print(f"Step {step}/3")
                print(f"{'='*50}")
                
                # 5-1. 현재 노드에서 액션 추출
                print(f"\n[{step}] 액션 추출 중...")
                all_actions = await extract_actions_from_page(page)
                print(f"   ✓ 전체 액션 수: {len(all_actions)}")
                
                if not all_actions:
                    print("   ⚠ 액션이 없습니다. 이동을 종료합니다.")
                    break
                
                # 5-2. 입력값 필요한 액션 필터링
                print(f"\n[{step}] 입력값 필요한 액션 필터링 중...")
                input_actions = filter_input_required_actions(all_actions)
                print(f"   ✓ 입력 액션 수: {len(input_actions)}")
                
                if not input_actions:
                    print("   ⚠ 입력 액션이 없습니다. 일반 액션 사용...")
                    if all_actions:
                        selected_action = all_actions[0]
                    else:
                        print("   ⚠ 사용 가능한 액션이 없습니다.")
                        break
                else:
                    # 5-3. 현재 입력 필드 값 수집
                    from utils.state_collector import collect_input_values
                    current_input_values = await collect_input_values(page)
                    
                    # 입력 액션을 딕셔너리 리스트로 변환
                    input_actions_dict = []
                    for action in input_actions:
                        action_target = action.get("action_target", "")
                        role = action.get("role", "")
                        name = action.get("name", "")
                        selector = action.get("selector", "")
                        
                        # 현재 입력 필드에 값이 있는지 확인
                        is_filled = False
                        current_value = ""
                        
                        if action_target in current_input_values:
                            is_filled = True
                            current_value = current_input_values[action_target]
                        elif role and name:
                            key = f"role={role} name={name}"
                            if key in current_input_values:
                                is_filled = True
                                current_value = current_input_values[key]
                        elif selector and selector in current_input_values:
                            is_filled = True
                            current_value = current_input_values[selector]
                        
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
                            "is_filled": is_filled,
                            "current_value": current_value if is_filled else ""
                        }
                        input_actions_dict.append(action_dict)
                    
                    # 5-4. LLM 호출 (filter-action)
                    print(f"\n[{step}] LLM 호출 중 (filter-action)...")
                    filtered_actions = await ai_service.filter_input_actions_with_run_memory(
                        input_actions=input_actions_dict,
                        run_id=UUID(run_id),
                        from_node_id=current_node_id
                    )
                    print(f"   ✓ 처리 가능한 액션 수: {len(filtered_actions)}")
                    
                    if not filtered_actions:
                        print("   ⚠ 처리 가능한 액션이 없습니다.")
                        break
                    
                    selected_action = filtered_actions[0]
                
                # 5-5. 액션 실행 및 엣지 생성
                print(f"\n[{step}] 액션 실행 중...")
                print(f"   - 타입: {selected_action.get('action_type')}")
                print(f"   - 타겟: {selected_action.get('action_target')}")
                print(f"   - 값: {selected_action.get('action_value', 'N/A')}")
                
                try:
                    edge = await perform_and_record_edge(
                        run_id=UUID(run_id),
                        from_node_id=current_node_id,
                        page=page,
                        action=selected_action
                    )
                    
                    print(f"   ✓ 엣지 생성: {edge['id']}")
                    print(f"   ✓ 결과: {edge.get('outcome')}")
                    
                    # from_node != to_node인 경우만 intent_label 확인 대상
                    if edge.get("from_node_id") and edge.get("to_node_id") and edge.get("from_node_id") != edge.get("to_node_id"):
                        created_edges.append(edge)
                        print(f"   ✓ intent_label 생성 대상 엣지로 추가됨")
                    
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

            # 6. 각 엣지의 intent_label 생성 완료까지 대기
            print("\n" + "=" * 50)
            print("Intent Label 생성 확인")
            print("=" * 50)
            
            if not created_edges:
                print("\n   ⚠ intent_label 확인 대상 엣지가 없습니다.")
            else:
                for idx, edge in enumerate(created_edges, 1):
                    edge_id = UUID(edge["id"])
                    print(f"\n[{idx}] 엣지 {edge_id}의 intent_label 확인 중...")
                    
                    intent_label = await wait_for_intent_label(edge_id, max_wait_seconds=30)
                    
                    if intent_label:
                        print(f"   ✓ intent_label 생성됨: '{intent_label}'")
                        print(f"   ✓ intent_label 길이: {len(intent_label)}자")
                        
                        # 검증
                        if len(intent_label) > 15:
                            print(f"   ⚠ 경고: intent_label이 15자를 초과합니다: {len(intent_label)}자")
                        else:
                            print(f"   ✓ intent_label이 15자 이내입니다")
                    else:
                        print(f"   ✗ intent_label 생성 타임아웃 (30초 대기 후에도 생성되지 않음)")

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
    # asyncio.run(test_interactive_action_selection(True))
    # asyncio.run(test_process_pending_actions())
    # asyncio.run(test_guess_edge_intent())

