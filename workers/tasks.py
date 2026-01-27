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
    
    _log("ACTION", run_id, f"최종 결과: 일반 액션={len(normal_actions)}, 처리 가능한 입력 액션={len(processable_input_actions)}")
    return normal_actions, processable_input_actions


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
            existing = edge_service.is_duplicate_action(run_id, from_node_id, action)
            if existing:
                _log("ACTION", run_id, f"[{idx}/{len(actions)}] 중복 액션 (성공), 스킵: {action_type} / {action_info}", "WARN")
                skipped_count += 1
                duplicate_count += 1
                continue
            
            # 2. 실패한 액션의 재시도 제한 체크 (락 획득 전에 체크)
            from repositories.edge_repository import count_failed_edges
            failed_count = count_failed_edges(
                run_id, from_node_id, action_type, action_target, action_value
            )
            MAX_FAILED_RETRIES = 3
            if failed_count >= MAX_FAILED_RETRIES:
                _log("ACTION", run_id, f"[{idx}/{len(actions)}] 실패한 액션 재시도 제한 초과 ({failed_count}회), 스킵: {action_type} / {action_info}", "WARN")
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
            existing_after_lock = edge_service.is_duplicate_action(run_id, from_node_id, action)
            if existing_after_lock:
                _log("ACTION", run_id, f"[{idx}/{len(actions)}] 락 획득 후 중복 액션 발견, 스킵: {action_type} / {action_info}", "WARN")
                release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
                skipped_count += 1
                continue
            
            # 5. 워커 생성
            process_action_worker.send(
                str(run_id),
                str(from_node_id),
                action
            )
            created_count += 1
            logger.debug(f"[{idx}/{len(actions)}] 워커 생성: {action_type} / {action_info}")
            # 워커가 큐에서 꺼내 실행될 때 락을 획득하므로, 생성 후 즉시 해제
            release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
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
    start_time = time.time()
    
    try:
        _log("NODE", run_id, f"워커 시작: node_id={node_id}")
        
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
            
            # 4. 수정사항이 있으면 process_pending_actions_worker 호출
            if has_changes:
                _log("NODE", run_id, f"[4/6] pending actions 처리 워커 시작")
                from workers.tasks import process_pending_actions_worker
                process_pending_actions_worker.send(str(run_id))
            else:
                _log("NODE", run_id, f"[4/6] pending actions 처리 스킵")
            
            # 5. 현재 노드에서 액션 추출 및 필터링
            _log("NODE", run_id, f"[5/6] 액션 추출 및 필터링 중...")
            normal_actions, processable_input_actions = await _extract_and_filter_actions(
                page, run_id, node_id
            )
            logger.debug(f"액션 추출 완료: 일반={len(normal_actions)}, 입력={len(processable_input_actions)}")
            
            # 액션이 없는 경우 경고
            if len(normal_actions) == 0 and len(processable_input_actions) == 0:
                _log("NODE", run_id, f"⚠ 액션이 없습니다. 페이지에서 액션을 찾을 수 없습니다.", "WARN")
                logger.debug(f"페이지 URL: {node_url}, 제목: {await page.title()}")
            
            # 6. 액션 필터링 및 워커 생성
            all_processable_actions = normal_actions + processable_input_actions
            if len(all_processable_actions) > 0:
                _log("NODE", run_id, f"액션 워커 생성 시작: {len(all_processable_actions)}개")
                await _create_action_workers(run_id, node_id, all_processable_actions)
                elapsed = time.time() - start_time
                _log("NODE", run_id, f"완료: {len(all_processable_actions)}개 액션 처리 (소요시간: {elapsed:.2f}초)")
            else:
                elapsed = time.time() - start_time
                _log("NODE", run_id, f"⚠ 액션 없음, 워커 생성 스킵 (소요시간: {elapsed:.2f}초)", "WARN")
        finally:
            # 락 해제
            release_node_lock(run_id, node_id)
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("NODE", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        logger.error(f"노드 워커 에러 발생 (소요시간: {elapsed:.2f}초): {e}", exc_info=True)
        release_node_lock(run_id, node_id)
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


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
        
        # 액션 처리 락 획득 (재시도 포함, 최대 5분 대기)
        # _create_action_workers에서 이미 획득했지만, 워커 시작 시 다시 확인
        # 락이 풀릴 때까지 최대 5분(300초) 대기
        lock_acquired = acquire_action_lock(
            run_id, from_node_id, action_type, action_target, action_value,
            timeout=300,  # 락 만료 시간
            retry_interval=0.5,  # 0.5초마다 재시도
            max_retries=600  # 최대 300초(5분) 대기
        )
        if not lock_acquired:
            _log("ACTION", run_id, f"액션 처리 락 획득 실패 (5분 대기 후), 종료", "WARN")
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
            
            # 4. 도착 노드 조회 (이미 페이지가 해당 노드에 있음)
            # 5. update_run_memory_with_ai 호출 및 수정사항 확인 (성공한 경우만)
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
                
                # 6. 수정사항이 있으면 process_pending_actions_worker 호출
                if has_changes:
                    logger.debug(f"pending actions 처리 워커 시작")
                    from workers.tasks import process_pending_actions_worker
                    process_pending_actions_worker.send(str(run_id))
            
            # 7. 현재 노드에서 액션 추출 및 필터링 (성공/실패 관계없이 진행)
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
                    
                    # 8. 액션 필터링 및 워커 생성
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
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


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
        
        # 1. process_pending_actions_with_run_memory 호출
        _log("PENDING", run_id, f"[1/2] pending actions 처리 가능 여부 확인 중...")
        ai_service = AiService()
        processable_actions = await ai_service.process_pending_actions_with_run_memory(
            run_id=run_id
        )
        
        _log("PENDING", run_id, f"[1/2] 처리 가능한 액션 수: {len(processable_actions)}")
        
        if not processable_actions:
            _log("PENDING", run_id, f"처리 가능한 액션 없음, 종료")
            return
        
        # 2. 각 액션에 대해 process_action_worker 워커 생성
        # pending action에는 from_node_id가 있음
        _log("PENDING", run_id, f"[2/2] pending actions 조회 중...")
        pending_action_service = PendingActionService()
        pending_actions = pending_action_service.list_pending_actions(
            run_id=run_id,
            from_node_id=None,
            status="pending"
        )
        
        _log("PENDING", run_id, f"[2/2] 전체 pending actions 수: {len(pending_actions)}")
        
        created_count = 0
        # 처리 가능한 액션과 매칭하여 from_node_id 찾기
        for idx, processable_action in enumerate(processable_actions, 1):
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
                    _log("PENDING", run_id, f"[2/2] [{idx}/{len(processable_actions)}] 워커 생성: {action_type} / {action_info} (from_node={from_node_id})")
                    matched = True
                    break
            
            if not matched:
                _log("PENDING", run_id, f"[2/2] [{idx}/{len(processable_actions)}] 매칭되는 pending action 없음: {action_type} / {action_info}", "WARN")
        
        elapsed = time.time() - start_time
        _log("PENDING", run_id, f"워커 완료: {created_count}개 워커 생성 (소요시간: {elapsed:.2f}초)")
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("PENDING", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        logger.error(f"pending actions 워커 에러 발생 (소요시간: {elapsed:.2f}초): {e}", exc_info=True)
