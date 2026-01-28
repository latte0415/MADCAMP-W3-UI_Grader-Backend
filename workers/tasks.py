"""
Dramatiq 작업(actor) 정의

@dramatiq.actor 데코레이터를 사용하여 비동기 작업을 정의합니다.
"""

import asyncio
import base64
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID

import dramatiq
from playwright.async_api import async_playwright

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from workers.broker import broker
from services.ai_service import AiService
from services.node_service import NodeService
from services.edge_service import EdgeService
from services.pending_action_service import PendingActionService
from utils.action_extractor import (
    extract_actions_from_page,
    filter_input_required_actions,
    parse_action_target,
)
from repositories.node_repository import get_node_by_id
from utils.logger import get_logger, set_context, clear_context
from exceptions.worker import WorkerTaskError

logger = get_logger(__name__)

# broker를 명시적으로 지정
dramatiq.set_broker(broker)


@dramatiq.actor
def example_task(message: str) -> str:
    """
    예시 작업 함수
    
    Args:
        message: 처리할 메시지
        
    Returns:
        처리 결과 문자열
    """
    logger.info(f"처리 중: {message}")
    result = f"처리 완료: {message}"
    return result


@dramatiq.actor(max_retries=3, time_limit=60000)
def long_running_task(data: dict) -> dict:
    """
    장시간 실행되는 작업 예시
    
    Args:
        data: 처리할 데이터 딕셔너리
    
    Returns:
        처리 결과 딕셔너리
    """
    logger.info(f"장시간 작업 시작: {data}")
    # 실제 작업 로직은 여기에 구현
    result = {"status": "completed", "data": data}
    return result


def _log(worker_type: str, run_id: UUID, message: str, level: str = "INFO"):
    """
    구조화된 로그 출력 (로거 기반)
    
    Args:
        worker_type: 워커 타입 (예: "NODE", "ACTION", "PENDING")
        run_id: 탐색 세션 ID
        message: 로그 메시지
        level: 로그 레벨 (INFO, WARN, ERROR)
    """
    set_context(run_id=str(run_id), worker_type=worker_type)
    log_level = getattr(logger, level.lower(), logger.info)
    log_level(message)


def _check_run_status(run_id: UUID) -> Optional[str]:
    """
    Run 상태를 확인하고, 작업을 계속할 수 있는지 확인합니다.
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        run 상태 문자열. 작업을 계속할 수 없으면 None 반환
    """
    from repositories.run_repository import get_run_by_id
    
    run = get_run_by_id(run_id)
    if not run:
        logger.warning(f"Run을 찾을 수 없습니다: {run_id}")
        return None
    
    status = run.get("status")
    
    # stopped, completed, failed 상태면 작업 중단
    if status in ["stopped", "completed", "failed"]:
        logger.info(f"Run 상태가 {status}이므로 작업을 중단합니다: {run_id}")
        return None
    
    # running 상태만 작업 계속
    if status != "running":
        logger.warning(f"Run 상태가 예상과 다릅니다: status={status}, run_id={run_id}")
        return None
    
    return status


def _run_async(coro):
    """동기 함수에서 비동기 함수를 실행하는 헬퍼"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _create_browser_context(storage_state: Optional[dict] = None):
    """
    Playwright 브라우저 컨텍스트 생성.
    
    Args:
        storage_state: 노드 복원용 storage state (localStorage, sessionStorage, cookies).
                       있으면 컨텍스트에 적용 후 페이지 로드.
    """
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    opts = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "viewport": {"width": 1280, "height": 720},
    }
    if storage_state:
        opts["storage_state"] = storage_state
    context = await browser.new_context(**opts)
    return playwright, browser, context


async def safe_close_browser_resources(browser, playwright, context=None, worker_type: str = "UNKNOWN"):
    """
    브라우저, 컨텍스트, Playwright 리소스를 안전하게 종료합니다.
    
    워커가 강제 종료되거나 브라우저가 이미 종료된 상태에서도 예외 없이 리소스를 정리합니다.
    
    Args:
        browser: Playwright Browser 객체 (None 가능)
        playwright: Playwright 객체 (None 가능)
        context: BrowserContext 객체 (None 가능)
        worker_type: 워커 타입 (로깅용, 예: "NODE", "ACTION")
    """
    # Context 종료 (가장 먼저)
    if context:
        try:
            await context.close()
        except Exception as e:
            logger.debug(f"[{worker_type}] 컨텍스트 종료 중 예외 (무시): {e}")
    
    # Browser 종료
    if browser:
        try:
            # 브라우저가 이미 종료되었는지 확인
            if hasattr(browser, 'is_connected'):
                if browser.is_connected():
                    await browser.close()
            else:
                # is_connected 속성이 없는 경우 그냥 시도
                await browser.close()
        except Exception as e:
            logger.debug(f"[{worker_type}] 브라우저 종료 중 예외 (무시): {e}")
    
    # Playwright 종료 (가장 마지막)
    if playwright:
        try:
            await playwright.stop()
        except Exception as e:
            logger.debug(f"[{worker_type}] Playwright 종료 중 예외 (무시): {e}")


async def _restore_input_values_on_page(page, input_values: Dict[str, str], run_id: UUID, worker_type: str = "NODE"):
    """
    노드 저장 입력값을 페이지에 복원합니다.
    role= name= 형식 또는 selector 키를 사용합니다.
    <hashed:...> 값(비밀번호 등)은 run_memory의 역해시 딕셔너리에서 원본 값을 가져와서 복원합니다.
    """
    if not input_values:
        return
    
    # run_memory에서 비밀번호 역해시 딕셔너리 가져오기
    password_hash_map = {}
    try:
        from repositories.ai_memory_repository import get_run_memory
        run_memory = get_run_memory(run_id)
        if run_memory:
            content = run_memory.get("content", {})
            password_hash_map = content.get("password_hash_map", {})
    except Exception as e:
        logger.debug(f"run_memory에서 비밀번호 역해시 딕셔너리 조회 실패 (계속 진행): {e}")
    
    restored = 0
    password_restored = 0
    for key, value in input_values.items():
        if not value:
            continue
        
        # 비밀번호 필드인 경우 (<hashed:...> 형식) 역해시 딕셔너리에서 원본 값 가져오기
        if isinstance(value, str) and value.startswith("<hashed:"):
            # 해시 값 추출: <hashed:abc123...> -> abc123...
            hash_value = value[8:-1]  # "<hashed:" (8자) 제거하고 ">" (1자) 제거
            
            # 역해시 딕셔너리에서 원본 값 찾기
            password_value = password_hash_map.get(hash_value)
            if password_value:
                value = password_value
                password_restored += 1
            else:
                # 역해시 딕셔너리에 없으면 스킵
                logger.debug(f"비밀번호 필드 복원 스킵 (역해시 딕셔너리에 없음): {key[:50]}... (hash={hash_value[:8]}...)")
                continue
        
        try:
            role, name = parse_action_target(key)
            if role and name:
                locator = page.get_by_role(role, name=name).first
            else:
                locator = page.locator(key).first
            await locator.fill(str(value)[:200])
            restored += 1
        except Exception as e:
            logger.debug(f"입력값 복원 스킵 key={key[:50]}: {e}")
    
    if restored:
        log_msg = f"노드 입력값 복원: {restored}개"
        if password_restored > 0:
            log_msg += f" (비밀번호 {password_restored}개 포함)"
        _log(worker_type, run_id, log_msg)


async def _extract_and_filter_actions(
    page,
    run_id: UUID,
    from_node_id: UUID
) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    """
    페이지에서 액션을 추출하고 필터링합니다.
    
    Returns:
        (일반 액션 리스트, 처리 가능한 입력 액션 리스트) 튜플
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


async def _create_action_workers(
    run_id: UUID,
    from_node_id: UUID,
    actions: list[Dict[str, Any]]
):
    """액션 리스트에 대해 워커를 생성합니다."""
    from workers.tasks import process_action_worker
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


@dramatiq.actor(max_retries=2, time_limit=600000)  # 5분 → 10분으로 증가
def process_node_worker(run_id: str, node_id: str):
    """
    노드를 부여받은 워커
    
    Args:
        run_id: 탐색 세션 ID (문자열)
        node_id: 노드 ID (문자열)
    """
    run_id_uuid = UUID(run_id)
    set_context(run_id=str(run_id_uuid), worker_type="NODE")
    logger.debug(f"워커 큐에서 메시지 수신: node_id={node_id}")
    _log("NODE", run_id_uuid, f"워커 시작: node_id={node_id}", "DEBUG")
    try:
        result = _run_async(_process_node_worker_async(run_id_uuid, UUID(node_id)))
        _log("NODE", run_id_uuid, f"워커 완료: node_id={node_id}", "DEBUG")
        return result
    except Exception as e:
        _log("NODE", run_id_uuid, f"워커 큐에서 에러: {e}", "ERROR")
        logger.error(f"워커 큐에서 에러 발생: {e}", exc_info=True)
        raise WorkerTaskError("process_node", run_id=run_id, original_error=e)


async def _process_node_worker_async(run_id: UUID, node_id: UUID):
    """process_node_worker의 비동기 구현"""
    from utils.lock_manager import acquire_node_lock, release_node_lock
    
    playwright = None
    browser = None
    context = None
    start_time = time.time()
    
    try:
        _log("NODE", run_id, f"워커 시작: node_id={node_id}")
        
        # Run 상태 확인 (stopped/completed/failed 상태면 즉시 종료)
        if _check_run_status(run_id) is None:
            _log("NODE", run_id, f"Run 상태 확인 실패, 작업 중단: node_id={node_id}", "WARN")
            return
        
        # 노드 처리 락 획득 (중복 처리 방지)
        if not acquire_node_lock(run_id, node_id, timeout=300):
            _log("NODE", run_id, f"노드 처리 락 획득 실패, 종료: {node_id}", "WARN")
            return
        
        try:
            # 1. 노드 조회 (아티팩트 포함: storage_state, input_values)
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
            
            # 2. Playwright 컨텍스트 생성 (노드 storage_state 적용) 후 해당 노드 URL로 이동
            playwright, browser, context = await _create_browser_context(storage_state=storage_state)
            page = await context.new_page()
            await page.goto(node["url"], wait_until="networkidle")
            if input_values:
                await _restore_input_values_on_page(page, input_values, run_id, "NODE")
                await asyncio.sleep(0.3)
            
            # 3. update_run_memory_with_ai 호출 및 수정사항 확인
            has_changes = False
            try:
                # 페이지가 완전히 로드될 때까지 추가 대기
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(0.5)  # 추가 안정화 대기
                
                # 일반 사용자가 인지할 수 있는 정보만 수집
                from utils.user_visible_info import collect_user_visible_info
                page_state = await collect_user_visible_info(page)
                
                # # 이미지 사용 시 (주석 처리)
                # screenshot_bytes = await page.screenshot(type="png")
                # image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                # image_size_mb = len(screenshot_bytes) / (1024 * 1024)
                # _log("NODE", run_id, f"[3/6] 스크린샷 촬영 완료: {image_size_mb:.2f}MB")
                
                logger.debug(f"페이지 정보 수집 완료: 제목={len(page_state.get('headings', []))}, 버튼={len(page_state.get('buttons', []))}, 링크={len(page_state.get('links', []))}")
                
                # auxiliary_data 준비
                auxiliary_data = {
                    "url": node_url,
                    "viewport": "1280x720"
                }
                
                ai_service = AiService()
                updated_memory, has_changes = await ai_service.update_run_memory_with_ai(
                    run_id=run_id,
                    auxiliary_data=auxiliary_data,
                    page_state=page_state  # 사용자 인지 가능한 정보만 전달
                    # image_base64 파라미터는 더 이상 사용하지 않음 (제거됨)
                )
                
                if has_changes:
                    _log("NODE", run_id, f"run_memory 수정사항 감지됨", "DEBUG")
                else:
                    logger.debug(f"run_memory 변경사항 없음")
            except Exception as e:
                error_msg = str(e)
                _log("NODE", run_id, f"[3/6] run_memory 업데이트 실패 (계속 진행): {error_msg}", "WARN")
                
                # 정책 위반 가능성 체크
                if "I'm sorry" in error_msg or "can't assist" in error_msg.lower():
                    _log("NODE", run_id, f"[3/6] ⚠ LLM이 정책상 이유로 응답 거부 가능성", "WARN")
                    _log("NODE", run_id, f"[3/6] Moderation 검사 결과를 확인하세요", "WARN")
                
                logger.warning(f"run_memory 업데이트 실패 (계속 진행): {error_msg}", exc_info=True)
                # 에러가 발생해도 계속 진행
                has_changes = False
            
            # 4. run_memory 업데이트 후 run 상태 재확인
            if _check_run_status(run_id) is None:
                _log("NODE", run_id, f"Run 상태 확인 실패, 작업 중단: node_id={node_id}", "WARN")
                return
            
            # 5. 수정사항이 있으면 process_pending_actions_worker 호출
            if has_changes:
                _log("NODE", run_id, f"[5/7] pending actions 처리 워커 시작")
                from workers.tasks import process_pending_actions_worker
                process_pending_actions_worker.send(str(run_id))
            else:
                _log("NODE", run_id, f"[5/7] pending actions 처리 스킵")
            
            # 6. 액션 추출 전 run 상태 재확인
            if _check_run_status(run_id) is None:
                _log("NODE", run_id, f"Run 상태 확인 실패, 작업 중단: node_id={node_id}", "WARN")
                return
            
            # 7. 현재 노드에서 액션 추출 및 필터링
            _log("NODE", run_id, f"[6/7] 액션 추출 및 필터링 중...")
            normal_actions, processable_input_actions = await _extract_and_filter_actions(
                page, run_id, node_id
            )
            logger.debug(f"액션 추출 완료: 일반={len(normal_actions)}, 입력={len(processable_input_actions)}")
            
            # 액션이 없는 경우 경고
            if len(normal_actions) == 0 and len(processable_input_actions) == 0:
                _log("NODE", run_id, f"⚠ 액션이 없습니다. 페이지에서 액션을 찾을 수 없습니다.", "WARN")
                logger.debug(f"페이지 URL: {node_url}, 제목: {await page.title()}")
            
            # 8. 액션 추출 후 run 상태 재확인
            if _check_run_status(run_id) is None:
                _log("NODE", run_id, f"Run 상태 확인 실패, 작업 중단: node_id={node_id}", "WARN")
                return
            
            # 9. 액션 필터링 및 워커 생성
            all_processable_actions = normal_actions + processable_input_actions
            if len(all_processable_actions) > 0:
                _log("NODE", run_id, f"액션 워커 생성 시작: {len(all_processable_actions)}개")
                await _create_action_workers(run_id, node_id, all_processable_actions)
                elapsed = time.time() - start_time
                _log("NODE", run_id, f"완료: {len(all_processable_actions)}개 액션 처리 (소요시간: {elapsed:.2f}초)")
            else:
                elapsed = time.time() - start_time
                _log("NODE", run_id, f"⚠ 액션 없음, 워커 생성 스킵 (소요시간: {elapsed:.2f}초)", "WARN")
                
                # 액션이 없는 경우에도 완료 체크 예약 (엣지 생성이 멈춘 경우 대비)
                from workers.tasks import check_graph_completion_worker
                from utils.lock_manager import is_completion_check_scheduled, mark_completion_check_scheduled
                from services.graph_completion_service import CHECK_INTERVAL_SECONDS
                
                if not is_completion_check_scheduled(run_id, window_seconds=30):
                    mark_completion_check_scheduled(run_id, window_seconds=30)
                    check_graph_completion_worker.send_with_options(
                        args=(str(run_id),),
                        delay=CHECK_INTERVAL_SECONDS * 1000
                    )
                    logger.debug(f"액션 없음 - 완료 체크 워커 예약 (안전장치): run_id={run_id}, {CHECK_INTERVAL_SECONDS}초 후")
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


@dramatiq.actor(max_retries=2, time_limit=600000)  # 5분 → 10분으로 증가
def process_action_worker(run_id: str, from_node_id: str, action: Dict[str, Any]):
    """
    액션을 부여받은 워커
    
    Args:
        run_id: 탐색 세션 ID (문자열)
        from_node_id: 시작 노드 ID (문자열)
        action: 액션 딕셔너리
    """
    run_id_uuid = UUID(run_id)
    action_type = action.get("action_type", "unknown")
    action_target = action.get("action_target", "unknown")
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
    
    set_context(run_id=str(run_id_uuid), worker_type="ACTION")
    logger.debug(f"워커 큐에서 메시지 수신: from_node={from_node_id}, action={action_type} / {action_info}")
    try:
        result = _run_async(_process_action_worker_async(run_id_uuid, UUID(from_node_id), action))
        logger.debug(f"워커 큐에서 완료: from_node={from_node_id}")
        return result
    except Exception as e:
        _log("ACTION", run_id_uuid, f"워커 큐에서 에러: {e}", "ERROR")
        logger.error(f"워커 큐에서 에러 발생: {e}", exc_info=True)
        raise WorkerTaskError("process_action", run_id=run_id, original_error=e)


async def _process_action_worker_async(
    run_id: UUID,
    from_node_id: UUID,
    action: Dict[str, Any]
):
    """process_action_worker의 비동기 구현"""
    from utils.lock_manager import acquire_action_lock, release_action_lock
    
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
                elapsed = time.time() - start_time
                _log("ACTION", run_id, f"액션 추출 스킵 (소요시간: {elapsed:.2f}초)", "DEBUG")
                # 스킵 시 바로 종료 (fallback 블록에서 락 없이 추출하면 중복 처리 발생)
                return
            else:
                try:
                    # 액션 추출 전에 페이지가 로드되었는지 확인
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass  # 타임아웃이어도 계속 진행
                    
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
                        await _create_action_workers(run_id, to_node_id, all_processable_actions)
                        elapsed = time.time() - start_time
                        _log("ACTION", run_id, f"완료: {len(all_processable_actions)}개 액션 처리 (소요시간: {elapsed:.2f}초)")
                    else:
                        elapsed = time.time() - start_time
                        if action_failed:
                            _log("ACTION", run_id, f"액션 실패 후 액션 없음 (소요시간: {elapsed:.2f}초)", "DEBUG")
                        else:
                            logger.debug(f"액션 없음, 워커 생성 스킵 (소요시간: {elapsed:.2f}초)")
                    
                    # 9. 그래프 완료 체크 워커 호출 (엣지 생성 후)
                    # 지연 실행하여 다른 워커들이 먼저 처리할 수 있도록 함
                    # 일정 시간 내 중복 호출 방지
                    from workers.tasks import check_graph_completion_worker
                    from utils.lock_manager import is_completion_check_scheduled, mark_completion_check_scheduled
                    
                    # 최근 10초 내에 이미 완료 체크가 예약되었는지 확인
                    if not is_completion_check_scheduled(run_id, window_seconds=10):
                        # 예약 표시 및 워커 호출
                        mark_completion_check_scheduled(run_id, window_seconds=10)
                        # dramatiq의 delay 옵션 사용 (밀리초 단위, 5초 후 실행)
                        check_graph_completion_worker.send_with_options(args=(str(run_id),), delay=5000)
                    else:
                        logger.debug(f"완료 체크 워커 호출 스킵 (이미 예약됨): run_id={run_id}")
                    
                    # 추가 안전장치: 액션 추출 후에도 완료 체크 예약 (엣지 생성이 멈춘 경우 대비)
                    # 최근 30초 내에 완료 체크가 예약되지 않았으면 예약
                    if not is_completion_check_scheduled(run_id, window_seconds=30):
                        from services.graph_completion_service import CHECK_INTERVAL_SECONDS
                        mark_completion_check_scheduled(run_id, window_seconds=30)
                        # CHECK_INTERVAL_SECONDS 후에 완료 체크 수행
                        check_graph_completion_worker.send_with_options(
                            args=(str(run_id),),
                            delay=CHECK_INTERVAL_SECONDS * 1000
                        )
                        logger.debug(f"추가 완료 체크 워커 예약 (안전장치): run_id={run_id}, {CHECK_INTERVAL_SECONDS}초 후")
                finally:
                    # 노드 처리 락 해제
                    release_node_lock(run_id, to_node_id)
                return  # 락을 획득한 경우 여기서 종료
        finally:
            # 락 해제
            release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("ACTION", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        logger.error(f"액션 워커 에러 발생 (소요시간: {elapsed:.2f}초): {e}", exc_info=True)
        release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
    finally:
        await safe_close_browser_resources(browser, playwright, context, "ACTION")


@dramatiq.actor(max_retries=2, time_limit=600000)  # 5분 → 10분으로 증가
def process_pending_actions_worker(run_id: str):
    """
    pending actions 처리 워커
    
    Args:
        run_id: 탐색 세션 ID (문자열)
    """
    run_id_uuid = UUID(run_id)
    _log("PENDING", run_id_uuid, f"워커 큐에서 시작됨")
    try:
        result = _run_async(_process_pending_actions_worker_async(run_id_uuid))
        _log("PENDING", run_id_uuid, f"워커 큐에서 완료")
        return result
    except Exception as e:
        _log("PENDING", run_id_uuid, f"워커 큐에서 에러: {e}", "ERROR")
        logger.error(f"워커 큐에서 에러 발생: {e}", exc_info=True)
        raise WorkerTaskError("process_pending_actions", run_id=run_id, original_error=e)


async def _process_pending_actions_worker_async(run_id: UUID):
    """process_pending_actions_worker의 비동기 구현"""
    start_time = time.time()
    
    try:
        _log("PENDING", run_id, f"워커 시작")
        
        # Run 상태 확인 (stopped/completed/failed 상태면 즉시 종료)
        if _check_run_status(run_id) is None:
            _log("PENDING", run_id, f"Run 상태 확인 실패, 작업 중단", "WARN")
            return
        
        # 1. process_pending_actions_with_run_memory 호출
        _log("PENDING", run_id, f"[1/2] pending actions 처리 가능 여부 확인 중...")
        ai_service = AiService()
        processable_actions = await ai_service.process_pending_actions_with_run_memory(
            run_id=run_id
        )
        
        _log("PENDING", run_id, f"[1/3] 처리 가능한 액션 수: {len(processable_actions)}")
        
        if not processable_actions:
            _log("PENDING", run_id, f"처리 가능한 액션 없음, 종료")
            return
        
        # 2. 처리 가능한 액션 확인 후 run 상태 재확인
        if _check_run_status(run_id) is None:
            _log("PENDING", run_id, f"Run 상태 확인 실패, 작업 중단", "WARN")
            return
        
        # 3. 각 액션에 대해 process_action_worker 워커 생성
        # pending action에는 from_node_id가 있음
        _log("PENDING", run_id, f"[2/3] pending actions 조회 중...")
        pending_action_service = PendingActionService()
        pending_actions = pending_action_service.list_pending_actions(
            run_id=run_id,
            from_node_id=None,
            status="pending"
        )
        
        _log("PENDING", run_id, f"[2/3] 전체 pending actions 수: {len(pending_actions)}")
        
        created_count = 0
        # 처리 가능한 액션과 매칭하여 from_node_id 찾기
        for idx, processable_action in enumerate(processable_actions, 1):
            # 각 액션 처리 전 run 상태 확인
            if _check_run_status(run_id) is None:
                _log("PENDING", run_id, f"Run 상태 확인 실패, 작업 중단 (처리 중: {idx}/{len(processable_actions)})", "WARN")
                break
            action_type = processable_action.get("action_type", "")
            action_target = processable_action.get("action_target", "")
            role = processable_action.get("role", "")
            name = processable_action.get("name", "")
            selector = processable_action.get("selector", "")
            
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
            
            # pending action에서 매칭되는 것 찾기
            matched = False
            for pending in pending_actions:
                if (pending.get("action_type") == action_type and
                    pending.get("action_target") == action_target):
                    from_node_id = UUID(pending.get("from_node_id"))
                    # 워커 생성
                    from workers.tasks import process_action_worker
                    process_action_worker.send(
                        str(run_id),
                        str(from_node_id),
                        processable_action
                    )
                    created_count += 1
                    _log("PENDING", run_id, f"[3/3] [{idx}/{len(processable_actions)}] 워커 생성: {action_type} / {action_info} (from_node={from_node_id})")
                    matched = True
                    break
            
            if not matched:
                _log("PENDING", run_id, f"[3/3] [{idx}/{len(processable_actions)}] 매칭되는 pending action 없음: {action_type} / {action_info}", "WARN")
        
        elapsed = time.time() - start_time
        _log("PENDING", run_id, f"워커 완료: {created_count}개 워커 생성 (소요시간: {elapsed:.2f}초)")
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("PENDING", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        logger.error(f"pending actions 워커 에러 발생 (소요시간: {elapsed:.2f}초): {e}", exc_info=True)


@dramatiq.actor(max_retries=2, time_limit=600000)
def check_graph_completion_worker(run_id: str):
    """
    그래프 구축 완료 여부를 체크하는 워커
    
    Args:
        run_id: 탐색 세션 ID (문자열)
    """
    run_id_uuid = UUID(run_id)
    set_context(run_id=str(run_id_uuid), worker_type="GRAPH_COMPLETION_CHECKER")
    logger.debug(f"그래프 완료 체크 워커 시작: run_id={run_id}")
    
    # 완료 체크 락 획득 (중복 실행 방지)
    from utils.lock_manager import acquire_completion_check_lock, release_completion_check_lock
    
    lock_acquired = acquire_completion_check_lock(
        run_id_uuid,
        timeout=30,  # 락 만료 시간: 30초
        retry_interval=0.1,
        max_retries=0  # 재시도 없음 - 다른 워커가 실행 중이면 즉시 종료
    )
    
    if not lock_acquired:
        # 다른 워커가 이미 완료 체크를 실행 중이면 스킵
        logger.debug(f"그래프 완료 체크 워커 스킵 (다른 워커가 실행 중): run_id={run_id}")
        clear_context()
        return
    
    try:
        from services.graph_completion_service import check_graph_completion, complete_graph_building, CHECK_INTERVAL_SECONDS
        
        # Run 상태 확인 (stopped/completed/failed 상태면 재스케줄링하지 않음)
        from repositories.run_repository import get_run_by_id
        run = get_run_by_id(run_id_uuid)
        if not run:
            logger.warning(f"Run을 찾을 수 없습니다: {run_id}")
            return
        
        status = run.get("status")
        if status != "running":
            logger.debug(f"Run이 이미 완료되었거나 중지됨: status={status}, 재스케줄링하지 않음")
            return
        
        # 완료 여부 체크
        is_complete = check_graph_completion(run_id_uuid)
        
        if is_complete:
            logger.info(f"그래프 구축 완료 감지: run_id={run_id}")
            # 완료 처리 및 full_analysis 시작
            complete_graph_building(run_id_uuid)
        else:
            logger.debug(f"그래프 구축 진행 중: run_id={run_id}, {CHECK_INTERVAL_SECONDS}초 후 재체크 예약")
            # 완료되지 않았으면 일정 시간 후 다시 체크하도록 재스케줄링
            # 이렇게 하면 엣지 생성이 멈춰도 주기적으로 완료 체크가 수행됨
            check_graph_completion_worker.send_with_options(
                args=(run_id,),
                delay=CHECK_INTERVAL_SECONDS * 1000  # 밀리초 단위
            )
    
    except Exception as e:
        logger.error(f"그래프 완료 체크 워커 에러 발생: {e}", exc_info=True)
        # 에러 발생 시에도 재스케줄링 (일시적인 오류일 수 있음)
        try:
            from services.graph_completion_service import CHECK_INTERVAL_SECONDS
            from repositories.run_repository import get_run_by_id
            run = get_run_by_id(run_id_uuid)
            if run and run.get("status") == "running":
                check_graph_completion_worker.send_with_options(
                    args=(run_id,),
                    delay=CHECK_INTERVAL_SECONDS * 1000
                )
                logger.debug(f"에러 발생 후 재스케줄링: run_id={run_id}")
        except Exception as reschedule_error:
            logger.error(f"재스케줄링 실패: {reschedule_error}", exc_info=True)
    finally:
        # 락 해제
        release_completion_check_lock(run_id_uuid)
        clear_context()


@dramatiq.actor(max_retries=0, time_limit=300000)  # 5분 타임아웃
def periodic_completion_check_worker():
    """
    주기적으로 모든 running 상태의 run을 체크하여 완료 여부를 확인하는 워커
    
    이 워커는 엣지 생성과 관계없이 독립적으로 실행되어,
    엣지 생성이 멈춰도 주기적으로 완료 체크를 수행합니다.
    """
    from repositories.run_repository import get_runs_by_status
    from services.graph_completion_service import CHECK_INTERVAL_SECONDS
    
    set_context(worker_type="PERIODIC_COMPLETION_CHECKER")
    logger.debug("주기적 완료 체크 워커 시작")
    
    try:
        # 모든 running 상태의 run 조회
        running_runs = get_runs_by_status("running")
        logger.debug(f"Running 상태의 run 수: {len(running_runs)}")
        
        if not running_runs:
            logger.debug("Running 상태의 run이 없습니다.")
            return
        
        # 각 run에 대해 완료 체크 워커 호출
        checked_count = 0
        for run in running_runs:
            run_id = run.get("id")
            if not run_id:
                continue
            
            try:
                # 완료 체크 워커 호출 (즉시 실행)
                check_graph_completion_worker.send(str(run_id))
                checked_count += 1
            except Exception as e:
                logger.warning(f"완료 체크 워커 호출 실패 (run_id={run_id}): {e}", exc_info=True)
        
        logger.debug(f"완료 체크 워커 호출 완료: {checked_count}개")
        
        # 다음 주기적 체크 예약 (CHECK_INTERVAL_SECONDS 후)
        periodic_completion_check_worker.send_with_options(
            args=(),
            delay=CHECK_INTERVAL_SECONDS * 1000  # 밀리초 단위
        )
        logger.debug(f"다음 주기적 완료 체크 예약: {CHECK_INTERVAL_SECONDS}초 후")
    
    except Exception as e:
        logger.error(f"주기적 완료 체크 워커 에러 발생: {e}", exc_info=True)
        # 에러 발생 시에도 다음 체크 예약 (일시적인 오류일 수 있음)
        try:
            from services.graph_completion_service import CHECK_INTERVAL_SECONDS
            periodic_completion_check_worker.send_with_options(
                args=(),
                delay=CHECK_INTERVAL_SECONDS * 1000
            )
        except Exception as reschedule_error:
            logger.error(f"재스케줄링 실패: {reschedule_error}", exc_info=True)
    finally:
        clear_context()


@dramatiq.actor(max_retries=1, time_limit=3600000)  # 1시간 타임아웃
def run_full_analysis_worker(run_id: str):
    """
    Full analysis를 실행하는 워커
    
    Args:
        run_id: 탐색 세션 ID (문자열)
    """
    # Import를 함수 시작 부분에 배치
    from repositories.run_repository import get_run_by_id, update_run
    from services.analysis_service import AnalysisService
    
    run_id_uuid = UUID(run_id)
    set_context(run_id=str(run_id_uuid), worker_type="FULL_ANALYSIS")
    logger.info(f"Full analysis 워커 시작: run_id={run_id}")
    
    try:
        
        # Run 상태 확인
        run = get_run_by_id(run_id_uuid)
        if not run:
            logger.error(f"Run을 찾을 수 없습니다: {run_id}")
            return
        
        status = run.get("status")
        if status != "completed":
            logger.warning(f"Run 상태가 completed가 아닙니다: status={status}")
            return
        
        # Full analysis 실행
        logger.info(f"Full analysis 실행 시작: run_id={run_id}")
        analysis_result = AnalysisService.run_full_analysis(run_id_uuid)
        
        # 결과를 DB에 저장
        from routers.evaluation import _save_analysis_results_to_db
        _save_analysis_results_to_db(run_id_uuid, analysis_result)
        
        logger.info(f"Full analysis 완료: run_id={run_id}")
    
    except Exception as e:
        logger.error(f"Full analysis 워커 에러 발생: {e}", exc_info=True)
        # 오류 발생 시에도 run 상태를 failed로 변경하지 않음
        # (그래프 구축은 완료되었으므로 completed 상태를 유지)
        # 대신 에러를 로깅하고, 필요시 수동으로 재시도할 수 있도록 함
        logger.warning(
            f"Full analysis 실행 실패 (run 상태는 completed 유지): run_id={run_id}, "
            f"에러={str(e)[:200]}. 필요시 수동으로 재시도하거나 로그를 확인하세요."
        )
        # run 상태는 completed로 유지 (그래프 구축은 성공적으로 완료되었으므로)
    finally:
        clear_context()
