"""
Deprecated Action Handler
"""
import time
import asyncio
from typing import Dict, Any
from uuid import UUID
import dramatiq
from utils.logger import get_logger, set_context
from exceptions.worker import WorkerTaskError
from workers.handlers.common import (
    _log, 
    _check_run_status, 
    _run_async, 
    _create_browser_context,
    safe_close_browser_resources, 
    _restore_input_values_on_page
)
from services.edge_service import EdgeService
from services.node_service import NodeService
from services.ai_service import AiService
from repositories.node_repository import get_node_by_id

logger = get_logger(__name__)

async def _create_action_workers_DEPRECATED(
    run_id: UUID,
    from_node_id: UUID,
    actions: list[Dict[str, Any]]
):
    """[DEPRECATED - DISABLED] 액션 리스트에 대해 워커를 생성합니다. 노드 기준 워커로 대체됨."""
    logger.warning(f"_create_action_workers_DEPRECATED 호출됨 (비활성화됨): run_id={run_id}, from_node_id={from_node_id}, actions={len(actions)}")
    _log("ACTION", run_id, f"⚠ DEPRECATED 함수 호출됨 - 비활성화됨. process_node_worker를 사용하세요.", "WARN")
    # DEPRECATED: This function is disabled. Use process_node_worker instead.
    # 함수 전체가 비활성화되었으므로 즉시 반환
    return
    # 아래 코드는 실행되지 않음 (비활성화됨)
    # from workers.tasks import process_action_worker
    from utils.lock_manager import acquire_action_lock, release_action_lock
    
    logger.debug(f"노드 {from_node_id}에서 {len(actions)}개 액션에 대해 워커 생성 시작")
    
    created_count = 0
    skipped_count = 0
    duplicate_count = 0
    retry_limit_count = 0
    lock_failed_count = 0
    
    # EdgeService를 한 번만 생성하여 재사용
    edge_service = EdgeService()
    
    # 동치 노드 체크를 위한 노드 정보 조회 (한 번만 조회)
    from_node = None
    equivalent_node_ids = []
    try:
        from_node = get_node_by_id(from_node_id)
        if from_node:
            state_hash = from_node.get("state_hash")
            a11y_hash = from_node.get("a11y_hash")
            input_state_hash = from_node.get("input_state_hash")
            if state_hash and a11y_hash and input_state_hash:
                from repositories.node_repository import find_equivalent_nodes
                equivalent_nodes = find_equivalent_nodes(
                    run_id, state_hash, a11y_hash, input_state_hash, exclude_node_id=from_node_id
                )
                equivalent_node_ids = [UUID(node["id"]) for node in equivalent_nodes]
                if equivalent_node_ids:
                    logger.debug(f"동치 노드 {len(equivalent_node_ids)}개 발견: {[str(nid)[:8] for nid in equivalent_node_ids[:5]]}")
    except Exception as e:
        logger.debug(f"동치 노드 조회 실패 (계속 진행): {e}")
    
    for idx, action in enumerate(actions, 1):
        action_type = action.get("action_type", "")
        action_target = action.get("action_target", "")
        action_value = action.get("action_value", "")
        role = action.get("role", "")
        name = action.get("name", "")
        selector = action.get("selector", "")
        
        # 액션 정보를 명확하게 표시
        action_info_parts = []
        if role and name:
            action_info_parts.append(f"role={role} name={name}")
        if selector:
            action_info_parts.append(f"selector={selector[:50]}")
        if not action_info_parts:
            action_target_short = action_target[:50] + "..." if len(action_target) > 50 else action_target
            action_info_parts.append(action_target_short)
        action_info = " / ".join(action_info_parts)
        
        try:
            # 1. 중복 체크를 먼저 수행 (락 획득 전에 체크하여 불필요한 락 경합 방지)
            # 실패한 엣지도 체크하여 중복 방지
            existing = edge_service.is_duplicate_action(run_id, from_node_id, action, check_failed=True)
            if existing:
                existing_outcome = existing.get("outcome", "unknown")
                _log("ACTION", run_id, f"[{idx}/{len(actions)}] 중복 액션 발견 (outcome={existing_outcome}), 스킵: {action_type} / {action_info}", "WARN")
                skipped_count += 1
                duplicate_count += 1
                continue
            
            # 1-1. 동치 노드에서 이미 성공한 액션이 있는지 확인
            equivalent_action_found = False
            if equivalent_node_ids:
                for equiv_node_id in equivalent_node_ids:
                    existing_equiv = edge_service.is_duplicate_action(run_id, equiv_node_id, action, check_failed=False)
                    if existing_equiv:
                        _log("ACTION", run_id, f"[{idx}/{len(actions)}] 동치 노드에서 이미 성공한 액션 발견, 스킵: {action_type} / {action_info} (동치 노드: {equiv_node_id})", "WARN")
                        skipped_count += 1
                        duplicate_count += 1
                        equivalent_action_found = True
                        break
            if equivalent_action_found:
                continue
            
            # 2. 실패한 액션의 재시도 제한 체크 (락 획득 전에 체크)
            from repositories.edge_repository import count_failed_edges
            failed_count = count_failed_edges(
                run_id, from_node_id, action_type, action_target, action_value
            )
            MAX_FAILED_RETRIES = 3
            if failed_count >= MAX_FAILED_RETRIES:
                _log("ACTION", run_id, f"[{idx}/{len(actions)}] 실패한 액션 재시도 제한 초과 ({failed_count}회 >= {MAX_FAILED_RETRIES}회), 스킵: {action_type} / {action_info}", "WARN")
                skipped_count += 1
                retry_limit_count += 1
                continue
            
            # 3. 락 획득 시도 (재시도 포함)
            # 락 획득 대기 시간 증가: 여러 워커가 동시에 같은 액션에 대한 락을 요청할 수 있으므로
            # 충분한 대기 시간이 필요함
            lock_acquired = acquire_action_lock(
                run_id, from_node_id, action_type, action_target, action_value,
                timeout=300,  # 락 만료 시간 (5분)
                retry_interval=0.2,  # 0.2초마다 재시도 (0.1초 → 0.2초로 증가)
                max_retries=50  # 최대 10초 대기 (0.2초 * 50) - 2초 → 10초로 증가
            )
            
            if not lock_acquired:
                # 락 획득 실패 시, 다른 워커가 처리 중일 수 있으므로 스킵
                _log("ACTION", run_id, f"[{idx}/{len(actions)}] 락 획득 실패 (10초 대기 후), 스킵: {action_type} / {action_info}", "WARN")
                skipped_count += 1
                lock_failed_count += 1
                continue
            
            # 4. 락 획득 후 다시 한 번 중복 체크 (락 획득 전과 후 사이에 다른 워커가 성공할 수 있음)
            # 실패한 엣지도 체크하여 중복 방지
            existing_after_lock = edge_service.is_duplicate_action(run_id, from_node_id, action, check_failed=True)
            if existing_after_lock:
                existing_outcome = existing_after_lock.get("outcome", "unknown")
                _log("ACTION", run_id, f"[{idx}/{len(actions)}] 락 획득 후 중복 액션 발견 (outcome={existing_outcome}), 스킵: {action_type} / {action_info}", "WARN")
                release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
                skipped_count += 1
                continue
            
            # 5. 워커 생성
            # 락을 해제하지 않고 유지하여 워커 실행 시점까지 중복 실행 방지
            # 워커가 실행되면 다시 락을 획득하려고 시도하지만, 이미 락이 있으면 즉시 획득됨
            # 락 만료 시간(timeout=300초)이 충분히 길어서 워커 실행까지 기다릴 수 있음
            process_action_worker.send(
                str(run_id),
                str(from_node_id),
                action
            )
            created_count += 1
            # 워커 생성 후 락 해제
            # 이전에는 워커 실행 시점까지 락을 유지했으나, 이로 인해 워커가 락을 획득하지 못하는 데드락 발생
            # 워커 큐에 넣은 후 바로 락을 해제하여 워커가 실행될 때 락을 획득할 수 있도록 함
            release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
            
            created_count += 1
            logger.debug(f"[{idx}/{len(actions)}] 워커 생성: {action_type} / {action_info} (락 해제됨)")
        except Exception as e:
            _log("ACTION", run_id, f"[{idx}/{len(actions)}] 워커 생성 실패: {e}", "ERROR")
            release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
            skipped_count += 1
    
    if created_count == 0:
        _log("ACTION", run_id, f"⚠ 워커 생성 실패: 모든 액션이 스킵됨 (스킵={skipped_count}, 전체={len(actions)})", "ERROR")
        _log("ACTION", run_id, f"  - 중복: {duplicate_count}, 재시도제한: {retry_limit_count}, 락실패: {lock_failed_count}", "ERROR")
        
        # 모든 액션이 스킵된 경우, 일정 시간 후 재시도
        # 락 실패나 일시적인 문제로 인한 스킵인 경우 재시도 가능
        # 하지만 중복이나 재시도 제한 초과인 경우는 재시도하지 않음
        if lock_failed_count > 0:
            # 락 실패가 있는 경우에만 재시도 (일시적인 경합일 수 있음)
            _log("ACTION", run_id, f"  - 락 실패로 인한 스킵 감지, 재시도 고려 필요", "INFO")
            # TODO: 재시도 메커니즘 구현
            # dramatiq의 지연된 작업 기능을 사용하거나, 별도의 재시도 큐를 구현할 수 있음
            # 현재는 로그만 남기고, 수동으로 재시도하거나 나중에 자동 재시도 메커니즘을 추가할 수 있음
    else:
        _log("ACTION", run_id, f"워커 생성 완료: 생성={created_count}, 스킵={skipped_count}, 전체={len(actions)}", "DEBUG")
        if skipped_count > 0:
            logger.debug(f"  - 중복: {duplicate_count}, 재시도제한: {retry_limit_count}, 락실패: {lock_failed_count}")


async def _process_action_worker_async_DEPRECATED(
    run_id: UUID,
    from_node_id: UUID,
    action: Dict[str, Any]
):
    """[DEPRECATED - DISABLED] process_action_worker의 비동기 구현 - 노드 기준 워커로 대체됨"""
    logger.warning(f"_process_action_worker_async_DEPRECATED 호출됨 (비활성화됨): run_id={run_id}, from_node_id={from_node_id}")
    _log("ACTION", run_id, f"⚠ DEPRECATED 함수 호출됨 - 비활성화됨. process_node_worker를 사용하세요.", "WARN")
    # DEPRECATED: This function is disabled. Use process_node_worker instead.
    # 함수 전체가 비활성화되었으므로 즉시 반환
    return
    from utils.lock_manager import acquire_action_lock, release_action_lock, release_node_lock
    
    playwright = None
    browser = None
    context = None
    start_time = time.time()
    
    action_type = action.get("action_type", "")
    action_target = action.get("action_target", "")
    action_value = action.get("action_value", "")
    role = action.get("role", "")
    name = action.get("name", "")
    selector = action.get("selector", "")
    
    # 액션 정보를 명확하게 표시
    action_info_parts = []
    if role and name:
        action_info_parts.append(f"role={role} name={name}")
    if selector:
        action_info_parts.append(f"selector={selector[:50]}")
    if not action_info_parts:
        action_target_short = action_target[:50] + "..." if len(action_target) > 50 else action_target
        action_info_parts.append(action_target_short)
    
    action_info = " / ".join(action_info_parts)
    action_value_short = (action_value[:30] + "...") if action_value and len(action_value) > 30 else (action_value or "")
    
    try:
        if action_value_short:
            _log("ACTION", run_id, f"워커 시작: {action_type} / {action_info} (값: {action_value_short})")
        else:
            _log("ACTION", run_id, f"워커 시작: {action_type} / {action_info}")
        
        # Run 상태 확인 (stopped/completed/failed 상태면 즉시 종료)
        if _check_run_status(run_id) is None:
            _log("ACTION", run_id, f"Run 상태 확인 실패, 작업 중단: {action_type} / {action_info}", "WARN")
            return
        
        # 워커 시작 전 다시 한 번 중복 체크 (락 획득 대기 방지)
        # 큐에 대기하는 동안 다른 워커가 처리를 완료했을 수 있음
        edge_service = EdgeService()
        existing = edge_service.is_duplicate_action(run_id, from_node_id, action, check_failed=True)
        if existing:
            existing_outcome = existing.get("outcome", "unknown")
            _log("ACTION", run_id, f"워커 시작 전 중복 액션 발견 (outcome={existing_outcome}), 종료: {action_type} / {action_info}", "INFO")
            return

        # 액션 처리 락 획득 (재시도 포함, 최대 5분 대기)
        # _create_action_workers에서 이미 획득했지만, 워커 시작 시 다시 확인
        # 락이 풀릴 때까지 최대 5분(300초) 대기
        # 단, _create_action_workers에서 락을 유지하고 있으므로, 여기서는 재시도 없이 즉시 확인
        lock_acquired = acquire_action_lock(
            run_id, from_node_id, action_type, action_target, action_value,
            timeout=300,  # 락 만료 시간
            retry_interval=0.1,  # 0.1초마다 재시도
            max_retries=10  # 최대 1초 대기 (락이 이미 획득되어 있으므로 빠르게 확인)
        )
        if not lock_acquired:
            # 락 획득 실패 시, 다른 워커가 처리 중이거나 락이 만료되었을 수 있음
            _log("ACTION", run_id, f"액션 처리 락 획득 실패 (다른 워커가 처리 중일 수 있음), 종료: {action_type} / {action_info}", "WARN")
            return
        
        # 락 획득 후 다시 한 번 재시도 제한 체크 (다른 워커가 이미 엣지를 생성했을 수 있음)
        from repositories.edge_repository import count_failed_edges
        failed_count_after_lock = count_failed_edges(
            run_id, from_node_id, action_type, action_target, action_value
        )
        MAX_FAILED_RETRIES = 3
        if failed_count_after_lock >= MAX_FAILED_RETRIES:
            _log("ACTION", run_id, f"락 획득 후 재시도 제한 재확인 ({failed_count_after_lock}회 >= {MAX_FAILED_RETRIES}회), 종료: {action_type} / {action_info}", "WARN")
            release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
            return
        
        try:
            # 1. Playwright 페이지 생성 및 from_node_id의 URL로 이동
            # 노드 조회 실패 시 재시도 (최대 3회, 1초 간격)
            from_node = None
            max_retries = 3
            retry_interval = 1.0
            
            node_service = NodeService()
            for retry_count in range(max_retries):
                from_node = node_service.get_node_with_artifacts(from_node_id)
                if from_node:
                    break
                
                if retry_count < max_retries - 1:
                    _log("ACTION", run_id, f"시작 노드 조회 실패 (재시도 {retry_count + 1}/{max_retries}): {from_node_id}", "WARN")
                    await asyncio.sleep(retry_interval)
                else:
                    _log("ACTION", run_id, f"시작 노드를 찾을 수 없습니다 (재시도 실패): {from_node_id}", "ERROR")
                    return
            
            if not from_node:
                _log("ACTION", run_id, f"시작 노드를 찾을 수 없습니다: {from_node_id}", "ERROR")
                return
            
            from_node_url = from_node.get("url", "unknown")
            logger.debug(f"시작 노드: {from_node_url}")
            
            artifacts = from_node.get("artifacts") or {}
            storage_state = artifacts.get("storage_state")
            input_values = artifacts.get("input_values")
            
            playwright, browser, context = await _create_browser_context(storage_state=storage_state)
            page = await context.new_page()
            await page.goto(from_node["url"], wait_until="networkidle")
            if input_values:
                await _restore_input_values_on_page(page, input_values, run_id, "ACTION")
                await asyncio.sleep(0.3)
            
            # 2. 액션 실행 및 엣지 생성 (guess_intent 포함)
            logger.debug(f"액션 실행 중: {action_type} / {action_info}")
            edge_service = EdgeService()
            edge = await edge_service.perform_and_record_edge(
                run_id=run_id,
                from_node_id=from_node_id,
                page=page,
                action=action
            )
            
            # 액션 실패 여부 확인
            action_failed = not edge or edge.get("outcome") != "success"
            if action_failed:
                error_msg = edge.get('error_msg') if edge else '엣지 생성 실패'
                # 실패 원인별 상세 로깅
                if "같은 노드로 돌아옴" in error_msg:
                    _log("ACTION", run_id, f"액션 실행 실패 (같은 노드로 돌아옴): {action_type} / {action_info}", "WARN")
                elif "요소를 찾을 수 없습니다" in error_msg:
                    _log("ACTION", run_id, f"액션 실행 실패 (요소 없음): {action_type} / {action_info}", "WARN")
                elif "Timeout" in error_msg:
                    _log("ACTION", run_id, f"액션 실행 실패 (타임아웃): {action_type} / {action_info}", "WARN")
                else:
                    _log("ACTION", run_id, f"액션 실행 실패 ({action_type} / {action_info}): {error_msg[:100]}", "WARN")
                # 실패한 경우에도 현재 노드에서 다음 액션으로 넘어가도록 처리
                to_node_id = from_node_id  # 같은 노드에 머물러 있음
                _log("ACTION", run_id, f"같은 노드에서 다음 액션으로 진행: {from_node_id}", "DEBUG")
            else:
                edge_id = edge.get("id", "unknown")
                logger.debug(f"액션 실행 성공: 엣지 ID={edge_id}")
                
                # 3. 도착 노드 확인
                to_node_id = edge.get("to_node_id")
                if not to_node_id:
                    _log("ACTION", run_id, f"도착 노드 없음 (같은 노드에서 계속 진행)", "WARN")
                    to_node_id = from_node_id  # 같은 노드에 머물러 있음
                else:
                    to_node_id = UUID(to_node_id)
                    if to_node_id == from_node_id:
                        _log("ACTION", run_id, f"⚠ 같은 노드로 돌아옴: {from_node_id} (다음 액션으로 진행)", "WARN")
                    else:
                        logger.debug(f"도착 노드: {to_node_id}")
            
            # 4. 액션 실행 후 run 상태 재확인
            if _check_run_status(run_id) is None:
                _log("ACTION", run_id, f"Run 상태 확인 실패, 작업 중단: {action_type} / {action_info}", "WARN")
                return
            
            # 5. 도착 노드 조회 (이미 페이지가 해당 노드에 있음)
            # 6. update_run_memory_with_ai 호출 및 수정사항 확인 (성공한 경우만)
            has_changes = False
            if not action_failed:
                # 액션이 성공한 경우에만 run_memory 업데이트
                try:
                    # 페이지가 완전히 로드될 때까지 추가 대기
                    await page.wait_for_load_state("networkidle", timeout=30000)
                    await asyncio.sleep(0.5)  # 추가 안정화 대기
                    
                    current_url = page.url
                    
                    # 일반 사용자가 인지할 수 있는 정보만 수집
                    from utils.user_visible_info import collect_user_visible_info
                    page_state = await collect_user_visible_info(page)
                    
                    logger.debug(f"페이지 정보 수집 완료: 제목={len(page_state.get('headings', []))}, 버튼={len(page_state.get('buttons', []))}, 링크={len(page_state.get('links', []))}")
                    
                    # auxiliary_data 준비
                    auxiliary_data = {
                        "url": current_url,
                        "viewport": "1280x720"
                    }
                    
                    ai_service = AiService()
                    updated_memory, has_changes = await ai_service.update_run_memory_with_ai(
                        run_id=run_id,
                        auxiliary_data=auxiliary_data,
                        page_state=page_state  # 사용자 인지 가능한 정보만 전달
                    )
                    
                    if has_changes:
                        logger.debug(f"run_memory 수정사항 감지됨")
                    else:
                        logger.debug(f"run_memory 변경사항 없음")
                except Exception as e:
                    error_msg = str(e)
                    _log("ACTION", run_id, f"run_memory 업데이트 실패 (계속 진행): {error_msg}", "WARN")
                    
                    # 정책 위반 가능성 체크
                    if "I'm sorry" in error_msg or "can't assist" in error_msg.lower():
                        _log("ACTION", run_id, f"⚠ LLM이 정책상 이유로 응답 거부 가능성", "WARN")
                    
                    logger.warning(f"run_memory 업데이트 실패 (계속 진행): {error_msg}", exc_info=True)
                    has_changes = False
                
                # 7. 수정사항이 있으면 process_pending_actions_worker 호출
                if has_changes:
                    logger.debug(f"pending actions 처리 워커 시작")
                    from workers.tasks import process_pending_actions_worker
                    process_pending_actions_worker.send(str(run_id))
            
            # 8. 액션 추출 전 run 상태 재확인
            if _check_run_status(run_id) is None:
                _log("ACTION", run_id, f"Run 상태 확인 실패, 작업 중단: {action_type} / {action_info}", "WARN")
                return
            
            # 9. 현재 노드에서 액션 추출 및 필터링 (성공/실패 관계없이 진행)
            # to_node_id가 UUID가 아닌 경우 변환
            if isinstance(to_node_id, str):
                to_node_id = UUID(to_node_id)
            elif to_node_id is None:
                to_node_id = from_node_id
            
            # 액션 추출 전에 다른 워커가 같은 노드를 처리 중인지 확인
            # 노드 처리 락이 있으면 다른 워커가 처리 중이므로 액션 추출 스킵
            from utils.lock_manager import acquire_node_lock, release_node_lock
            node_lock_acquired = acquire_node_lock(run_id, to_node_id, timeout=300)
            if not node_lock_acquired:
                _log("ACTION", run_id, f"노드 처리 락 획득 실패 (다른 워커가 처리 중), 액션 추출 스킵: {to_node_id}", "WARN")
                # 스킵 시 바로 종료 (fallback 블록에서 락 없이 추출하면 중복 처리 발생)
                return
            else:
                try:
                    # 액션 추출 전에 페이지가 로드되었는지 확인
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass  # 타임아웃이어도 계속 진행
                    
                    # This import might be circular if we put extract function in handlers too.
                    # Assuming we keep extractor as utility or import from common?
                    # The extract helper is also being moved to node_handler or common.
                    # For now, let's assuming it's imported from action_extractor which is fine.
                    # BUT _extract_and_filter_actions IS IN TASKS.py
                    # We need to move _extract_and_filter_actions to node_handler or common.
                    from workers.tasks import _extract_and_filter_actions
                    
                    normal_actions, processable_input_actions = await _extract_and_filter_actions(
                        page, run_id, to_node_id
                    )
                    logger.debug(f"액션 추출 완료: 일반={len(normal_actions)}, 입력={len(processable_input_actions)}")
                    
                    # 10. 액션 추출 후 run 상태 재확인
                    if _check_run_status(run_id) is None:
                        _log("ACTION", run_id, f"Run 상태 확인 실패, 작업 중단: {action_type} / {action_info}", "WARN")
                        return
                    
                    # 11. 액션 필터링 및 워커 생성
                    all_processable_actions = normal_actions + processable_input_actions
                    if len(all_processable_actions) > 0:
                        _log("ACTION", run_id, f"액션 워커 생성 시작: {len(all_processable_actions)}개 (노드: {to_node_id})")
                        await _create_action_workers_DEPRECATED(run_id, to_node_id, all_processable_actions)
                        _log("ACTION", run_id, f"완료: {len(all_processable_actions)}개 액션 처리")
                    else:
                        if action_failed:
                            _log("ACTION", run_id, f"액션 실패 후 액션 없음", "DEBUG")
                        else:
                            logger.debug(f"액션 없음, 워커 생성 스킵")
                    
                    # 9. 그래프 완료 체크 워커 호출 (엣지 생성 후)
                    from workers.tasks import check_graph_completion_worker
                    from utils.lock_manager import is_completion_check_scheduled, mark_completion_check_scheduled
                    
                    # 최근 10초 내에 이미 완료 체크가 예약되었는지 확인
                    if not is_completion_check_scheduled(run_id, window_seconds=10):
                        mark_completion_check_scheduled(run_id, window_seconds=10)
                        check_graph_completion_worker.send_with_options(args=(str(run_id),), delay=5000)
                    else:
                        logger.debug(f"완료 체크 워커 호출 스킵 (이미 예약됨): run_id={run_id}")
                    
                    if not is_completion_check_scheduled(run_id, window_seconds=30):
                        from services.graph_completion_service import CHECK_INTERVAL_SECONDS
                        mark_completion_check_scheduled(run_id, window_seconds=30)
                        check_graph_completion_worker.send_with_options(
                            args=(str(run_id),),
                            delay=CHECK_INTERVAL_SECONDS * 1000
                        )
                finally:
                    # 노드 처리 락 해제
                    release_node_lock(run_id, to_node_id)
                return  # 락을 획득한 경우 여기서 종료
        finally:
            # 락 해제
            release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
        
    except Exception as e:
        _log("ACTION", run_id, f"에러 발생: {e}", "ERROR")
        logger.error(f"액션 워커 에러 발생: {e}", exc_info=True)
        release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
    finally:
        await safe_close_browser_resources(browser, playwright, context, "ACTION")
