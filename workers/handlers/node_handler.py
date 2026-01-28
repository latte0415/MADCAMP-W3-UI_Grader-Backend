"""
Node Worker Handler
"""
import time
import asyncio
from typing import Dict, Any
from uuid import UUID
from utils.logger import get_logger, set_context
from exceptions.worker import WorkerTaskError
from workers.handlers.common import (
    _log, 
    _check_run_status, 
    _create_browser_context,
    safe_close_browser_resources, 
    _restore_input_values_on_page
)
from services.edge_service import EdgeService
from services.node_service import NodeService
from services.ai_service import AiService
from utils.action_extractor import (
    extract_actions_from_page,
    filter_input_required_actions
)

logger = get_logger(__name__)

async def _extract_and_filter_actions(
    page,
    run_id: UUID,
    from_node_id: UUID
) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    """
    페이지에서 액션을 추출하고 필터링합니다.
    """
    # 액션 추출
    _log("ACTION", run_id, f"페이지에서 액션 추출 시작...")
    all_actions = await extract_actions_from_page(page)
    _log("ACTION", run_id, f"전체 액션 추출 완료: {len(all_actions)}개")
    
    if len(all_actions) == 0:
        _log("ACTION", run_id, f"⚠ 페이지에서 액션을 찾을 수 없습니다", "WARN")
        return [], []
    
    # 입력 액션과 일반 액션 분리
    input_actions = filter_input_required_actions(all_actions)
    normal_actions = [a for a in all_actions if a not in input_actions]
    _log("ACTION", run_id, f"액션 분류: 일반={len(normal_actions)}, 입력={len(input_actions)}")
    
    # 입력 액션 필터링
    processable_input_actions = []
    if input_actions:
        _log("ACTION", run_id, f"입력 액션 필터링 시작: {len(input_actions)}개")
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
        
        # LLM으로 필터링
        _log("ACTION", run_id, f"LLM으로 입력 액션 필터링 중: {len(input_actions_dict)}개")
        ai_service = AiService()
        processable_input_actions = await ai_service.filter_input_actions_with_run_memory(
            input_actions=input_actions_dict,
            run_id=run_id,
            from_node_id=from_node_id
        )
        _log("ACTION", run_id, f"LLM 필터링 완료: 처리 가능한 입력 액션={len(processable_input_actions)}개")
    else:
        _log("ACTION", run_id, f"입력 액션 없음, 필터링 스킵")
    
    # 같은 노드로 돌아오는 액션 필터링 (이미 실패한 액션 제외)
    # 효율성을 위해 한 번에 실패 엣지 조회
    from repositories.edge_repository import get_edges_by_run_id
    all_edges = get_edges_by_run_id(run_id)
    
    # 같은 노드로 돌아온 실패 엣지 집합 생성 (빠른 조회를 위해)
    same_node_failed_actions = set()
    for edge in all_edges:
        if (edge.get("from_node_id") == str(from_node_id) and
            edge.get("outcome") == "fail" and
            edge.get("error_msg") and
            "같은 노드로 돌아옴" in edge.get("error_msg", "")):
            # 액션 키 생성: (action_type, action_target, action_value)
            action_key = (
                edge.get("action_type", ""),
                edge.get("action_target", ""),
                edge.get("action_value", "") or ""
            )
            same_node_failed_actions.add(action_key)
    
    # 일반 액션 필터링
    filtered_normal_actions = []
    normal_key_check = set()
    for action in normal_actions:
        action_key = (
            action.get("action_type", ""),
            action.get("action_target", ""),
            action.get("action_value", "") or ""
        )
        if action_key not in same_node_failed_actions:
            filtered_normal_actions.append(action)
    
    # 입력 액션 필터링
    filtered_input_actions = []
    for action in processable_input_actions:
        action_key = (
            action.get("action_type", ""),
            action.get("action_target", ""),
            action.get("action_value", "") or ""
        )
        if action_key not in same_node_failed_actions:
            filtered_input_actions.append(action)
    
    filtered_count = (len(normal_actions) - len(filtered_normal_actions) + 
                     len(processable_input_actions) - len(filtered_input_actions))
    if filtered_count > 0:
        _log("ACTION", run_id, f"같은 노드로 돌아오는 액션 {filtered_count}개 필터링됨", "DEBUG")
    
    _log("ACTION", run_id, f"최종 결과: 일반 액션={len(filtered_normal_actions)}, 처리 가능한 입력 액션={len(filtered_input_actions)}")
    return filtered_normal_actions, filtered_input_actions

async def process_node_worker_async(run_id: UUID, node_id: UUID):
    """process_node_worker의 비동기 구현"""
    from utils.lock_manager import acquire_node_lock, release_node_lock
    from services.graph_completion_service import check_graph_completion, complete_graph_building
    # Import actor to spawn
    from workers.tasks import process_node_worker
    
    playwright = None
    browser = None
    context = None
    start_time = time.time()
    
    try:
        _log("NODE", run_id, f"워커 시작: node_id={node_id}")
        
        # Run 상태 확인
        if _check_run_status(run_id) is None:
            _log("NODE", run_id, f"Run 상태 확인 실패, 작업 중단: node_id={node_id}", "WARN")
            return
        
        # 노드 처리 락 획득
        if not acquire_node_lock(run_id, node_id, timeout=300):
            _log("NODE", run_id, f"노드 처리 락 획득 실패, 종료: {node_id}", "WARN")
            return
        
        try:
            # 1. 노드 조회
            node_service = NodeService()
            node = node_service.get_node_with_artifacts(node_id)
            if not node:
                _log("NODE", run_id, f"노드를 찾을 수 없습니다: {node_id}", "ERROR")
                return
            
            node_url = node.get("url", "unknown")
            _log("NODE", run_id, f"노드 처리 시작: URL={node_url}")
            
            artifacts = node.get("artifacts") or {}
            storage_state = artifacts.get("storage_state")
            input_values = artifacts.get("input_values")
            
            # 2. Playwright 컨텍스트 생성 및 이동
            playwright, browser, context = await _create_browser_context(storage_state=storage_state)
            page = await context.new_page()
            await page.goto(node["url"], wait_until="networkidle")
            if input_values:
                await _restore_input_values_on_page(page, input_values, run_id, "NODE")
                await asyncio.sleep(0.3)
            
            # 3. update_run_memory_with_ai
            has_changes = False
            try:
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(0.5)
                
                from utils.user_visible_info import collect_user_visible_info
                page_state = await collect_user_visible_info(page)
                
                auxiliary_data = {
                    "url": node_url,
                    "viewport": "1280x720"
                }
                
                ai_service = AiService()
                updated_memory, has_changes = await ai_service.update_run_memory_with_ai(
                    run_id=run_id,
                    auxiliary_data=auxiliary_data,
                    page_state=page_state
                )
                
                if has_changes:
                    _log("NODE", run_id, f"run_memory 수정사항 감지됨", "DEBUG")
                else:
                    logger.debug(f"run_memory 변경사항 없음")
            except Exception as e:
                error_msg = str(e)
                _log("NODE", run_id, f"[3/6] run_memory 업데이트 실패 (계속 진행): {error_msg}", "WARN")
                logger.warning(f"run_memory 업데이트 실패 (계속 진행): {error_msg}", exc_info=True)
                has_changes = False
            
            if _check_run_status(run_id) is None:
                _log("NODE", run_id, f"Run 상태 확인 실패, 작업 중단: node_id={node_id}", "WARN")
                return
            
            # 5. Pending Actions 확인
            if has_changes:
                _log("NODE", run_id, f"[5/7] pending actions 처리 워커 시작")
                from workers.tasks import process_pending_actions_worker
                process_pending_actions_worker.send(str(run_id))
            else:
                _log("NODE", run_id, f"[5/7] pending actions 처리 스킵")
            
            if _check_run_status(run_id) is None:
                return
            
            # 7. 액션 추출 및 필터링
            _log("NODE", run_id, f"[6/7] 액션 추출 및 필터링 중...")
            normal_actions, processable_input_actions = await _extract_and_filter_actions(
                page, run_id, node_id
            )
            logger.debug(f"액션 추출 완료: 일반={len(normal_actions)}, 입력={len(processable_input_actions)}")
            
            # 액션 처리 (Sequential)
            all_processable_actions = normal_actions + processable_input_actions
            
            if len(all_processable_actions) > 0:
                _log("NODE", run_id, f"액션 순차 처리 시작: {len(all_processable_actions)}개 (노드: {node_id})", "INFO")
                
                edge_service = EdgeService()
                node_service = NodeService()
                processed_count = 0
                
                for idx, action in enumerate(all_processable_actions):
                    if _check_run_status(run_id) is None:
                        _log("NODE", run_id, f"Run 상태 확인 실패, 액션 처리 중단 ({idx}/{len(all_processable_actions)})", "WARN")
                        break
                        
                    if check_graph_completion(run_id):
                        _log("NODE", run_id, "그래프 빌딩 완료 조건 도달, 액션 처리 중단", "INFO")
                        complete_graph_building(run_id)
                        break

                    action_type = action.get("action_type")
                    action_target = action.get("action_target", "unknown")
                    
                    # 액션 정보 로깅
                    _log("NODE", run_id, f"[{idx+1}/{len(all_processable_actions)}] 액션 실행: {action_type} / {action_target[:50]}", "DEBUG")
                    
                    try:
                        # 페이지 상태 초기화 (새로운 액션을 위해 노드 URL로 다시 이동)
                        current_page_url = page.url
                        target_url = node["url"]
                        
                        norm_current = current_page_url.rstrip("/")
                        norm_target = target_url.rstrip("/")
                        
                        if idx > 0 or norm_current != norm_target:
                            try:
                                await page.goto(target_url, wait_until="networkidle")
                                if input_values:
                                    await _restore_input_values_on_page(page, input_values, run_id, "NODE")
                                    await asyncio.sleep(0.3)
                            except Exception as nav_e:
                                logger.warning(f"액션 실행 전 페이지 리로드 실패: {nav_e}")
                                continue
                        
                        # 액션 실행 및 엣지 기록
                        edge = await edge_service.perform_and_record_edge(
                            run_id=run_id,
                            from_node_id=node_id, # 현재 처리 중인 노드가 from_node
                            page=page,
                            action=action
                        )
                        
                        processed_count += 1
                        
                        # 결과 처리
                        if edge and edge.get("outcome") == "success":
                            new_to_node_id = edge.get("to_node_id")
                            
                            try:
                                from utils.user_visible_info import collect_user_visible_info
                                page_state = await collect_user_visible_info(page)
                                
                                auxiliary_data = {
                                    "url": page.url,
                                    "viewport": "1280x720"
                                }
                                
                                ai_service = AiService()
                                updated_memory, has_changes = await ai_service.update_run_memory_with_ai(
                                    run_id=run_id,
                                    auxiliary_data=auxiliary_data,
                                    page_state=page_state
                                )
                                
                                if has_changes:
                                    logger.debug(f"run_memory 수정사항 감지됨 (액션 처리 중)")
                                    from workers.tasks import process_pending_actions_worker
                                    process_pending_actions_worker.send(str(run_id))
                            except Exception as ai_e:
                                logger.warning(f"run_memory 업데이트 실패 (계속 진행): {ai_e}")

                            if new_to_node_id:
                                new_node_uuid = UUID(new_to_node_id)
                                if new_node_uuid != node_id: # 다른 노드로 이동한 경우
                                    process_node_worker.send(str(run_id), str(new_node_uuid))
                                    _log("NODE", run_id, f"새 노드 발견, 워커 생성: {new_node_uuid}", "INFO")
                        
                    except Exception as action_e:
                        logger.error(f"액션 실행 중 에러: {action_e}", exc_info=True)
                        continue
                
                elapsed = time.time() - start_time
                _log("NODE", run_id, f"완료: {processed_count}/{len(all_processable_actions)}개 액션 순차 처리 (소요시간: {elapsed:.2f}초)", "INFO")
                
            else:
                elapsed = time.time() - start_time
                logger.debug(f"액션 없음 (소요시간: {elapsed:.2f}초)")
            
            # 9. 그래프 완료 체크 워커 호출
            from workers.tasks import check_graph_completion_worker
            from utils.lock_manager import is_completion_check_scheduled, mark_completion_check_scheduled
            
            if not is_completion_check_scheduled(run_id, window_seconds=10):
                mark_completion_check_scheduled(run_id, window_seconds=10)
                check_graph_completion_worker.send_with_options(args=(str(run_id),), delay=5000)
            
            if not is_completion_check_scheduled(run_id, window_seconds=30):
                from services.graph_completion_service import CHECK_INTERVAL_SECONDS
                mark_completion_check_scheduled(run_id, window_seconds=30)
                check_graph_completion_worker.send_with_options(
                    args=(str(run_id),),
                    delay=CHECK_INTERVAL_SECONDS * 1000
                )

        finally:
            # 락 해제
            release_node_lock(run_id, node_id)
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("NODE", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        logger.error(f"노드 워커 에러 발생 (소요시간: {elapsed:.2f}초): {e}", exc_info=True)
        release_node_lock(run_id, node_id)
    finally:
        await safe_close_browser_resources(browser, playwright, context, "NODE")
