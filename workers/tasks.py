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
from utils.action_extractor import extract_actions_from_page, filter_input_required_actions
from repositories.node_repository import get_node_by_id

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
    print(f"[Worker] 처리 중: {message}")
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
    print(f"[Worker] 장시간 작업 시작: {data}")
    # 실제 작업 로직은 여기에 구현
    result = {"status": "completed", "data": data}
    return result


def _log(worker_type: str, run_id: UUID, message: str, level: str = "INFO"):
    """
    구조화된 로그 출력
    
    Args:
        worker_type: 워커 타입 (예: "NODE", "ACTION", "PENDING")
        run_id: 탐색 세션 ID
        message: 로그 메시지
        level: 로그 레벨 (INFO, WARN, ERROR)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_id_short = str(run_id)[:8]
    print(f"[{timestamp}] [{level}] [{worker_type}] [run:{run_id_short}] {message}")


def _run_async(coro):
    """동기 함수에서 비동기 함수를 실행하는 헬퍼"""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _create_browser_context():
    """Playwright 브라우저 컨텍스트 생성"""
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        viewport={'width': 1280, 'height': 720}
    )
    return playwright, browser, context


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
    
    _log("ACTION", run_id, f"노드 {from_node_id}에서 {len(actions)}개 액션에 대해 워커 생성 시작")
    
    created_count = 0
    skipped_count = 0
    
    for idx, action in enumerate(actions, 1):
        action_type = action.get("action_type", "")
        action_target = action.get("action_target", "")
        action_value = action.get("action_value", "")
        action_target_short = action_target[:50] + "..." if len(action_target) > 50 else action_target
        
        # 락 획득 시도 (선택적)
        lock_acquired = acquire_action_lock(
            run_id, from_node_id, action_type, action_target, action_value, timeout=30
        )
        
        if not lock_acquired:
            _log("ACTION", run_id, f"[{idx}/{len(actions)}] 락 획득 실패, 스킵: {action_type} / {action_target_short}", "WARN")
            skipped_count += 1
            continue
        
        try:
            # 중복 체크 (DB 제약조건)
            edge_service = EdgeService()
            existing = edge_service.is_duplicate_action(run_id, from_node_id, action)
            if existing:
                _log("ACTION", run_id, f"[{idx}/{len(actions)}] 중복 액션, 스킵: {action_type} / {action_target_short}", "WARN")
                release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
                skipped_count += 1
                continue
            
            # 워커 생성
            process_action_worker.send(
                str(run_id),
                str(from_node_id),
                action
            )
            created_count += 1
            _log("ACTION", run_id, f"[{idx}/{len(actions)}] 워커 생성: {action_type} / {action_target_short}")
            # 워커가 시작되면 락 해제 (워커 내부에서 처리)
        except Exception as e:
            _log("ACTION", run_id, f"[{idx}/{len(actions)}] 워커 생성 실패: {e}", "ERROR")
            release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
            skipped_count += 1
    
    _log("ACTION", run_id, f"워커 생성 완료: 생성={created_count}, 스킵={skipped_count}, 전체={len(actions)}")


@dramatiq.actor(max_retries=2, time_limit=300000)
def process_node_worker(run_id: str, node_id: str):
    """
    노드를 부여받은 워커
    
    Args:
        run_id: 탐색 세션 ID (문자열)
        node_id: 노드 ID (문자열)
    """
    run_id_uuid = UUID(run_id)
    _log("NODE", run_id_uuid, f"워커 큐에서 시작됨: node_id={node_id}")
    try:
        result = _run_async(_process_node_worker_async(run_id_uuid, UUID(node_id)))
        _log("NODE", run_id_uuid, f"워커 큐에서 완료: node_id={node_id}")
        return result
    except Exception as e:
        _log("NODE", run_id_uuid, f"워커 큐에서 에러: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        raise


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
            # 1. 노드 조회
            _log("NODE", run_id, f"[1/6] 노드 조회 중: {node_id}")
            node = get_node_by_id(node_id)
            if not node:
                _log("NODE", run_id, f"노드를 찾을 수 없습니다: {node_id}", "ERROR")
                return
            
            node_url = node.get("url", "unknown")
            _log("NODE", run_id, f"[1/6] 노드 조회 완료: URL={node_url}")
            
            # 2. Playwright 페이지 생성 및 해당 노드 URL로 이동
            _log("NODE", run_id, f"[2/6] 브라우저 컨텍스트 생성 중...")
            playwright, browser, context = await _create_browser_context()
            page = await context.new_page()
            await page.goto(node["url"], wait_until="networkidle")
            _log("NODE", run_id, f"[2/6] 페이지 로드 완료: {node_url}")
            
            # 3. update_run_memory_with_ai 호출 및 수정사항 확인
            _log("NODE", run_id, f"[3/6] 스크린샷 촬영 및 run_memory 업데이트 중...")
            screenshot_bytes = await page.screenshot(type="png")
            image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            ai_service = AiService()
            updated_memory, has_changes = await ai_service.update_run_memory_with_ai(
                image_base64=image_base64,
                run_id=run_id,
                auxiliary_data=None
            )
            
            if has_changes:
                _log("NODE", run_id, f"[3/6] run_memory 수정사항 감지됨")
            else:
                _log("NODE", run_id, f"[3/6] run_memory 변경사항 없음")
            
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
            _log("NODE", run_id, f"[5/6] 액션 추출 완료: 일반={len(normal_actions)}, 입력={len(processable_input_actions)}")
            
            # 액션이 없는 경우 경고
            if len(normal_actions) == 0 and len(processable_input_actions) == 0:
                _log("NODE", run_id, f"[5/6] ⚠ 액션이 없습니다. 페이지에서 액션을 찾을 수 없습니다.", "WARN")
                _log("NODE", run_id, f"[5/6] 페이지 URL: {node_url}")
                _log("NODE", run_id, f"[5/6] 페이지 제목: {await page.title()}")
            
            # 6. 액션 필터링 및 워커 생성
            all_processable_actions = normal_actions + processable_input_actions
            _log("NODE", run_id, f"[6/6] 워커 생성 시작: 총 {len(all_processable_actions)}개 액션")
            
            if len(all_processable_actions) > 0:
                await _create_action_workers(run_id, node_id, all_processable_actions)
            else:
                _log("NODE", run_id, f"[6/6] 워커 생성 스킵: 액션이 없음")
            
            elapsed = time.time() - start_time
            _log("NODE", run_id, f"워커 완료: {len(all_processable_actions)}개 액션에 대해 워커 생성 (소요시간: {elapsed:.2f}초)")
        finally:
            # 락 해제
            release_node_lock(run_id, node_id)
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("NODE", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        import traceback
        traceback.print_exc()
        release_node_lock(run_id, node_id)
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


@dramatiq.actor(max_retries=2, time_limit=300000)
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
    _log("ACTION", run_id_uuid, f"워커 큐에서 시작됨: from_node={from_node_id}, action={action_type} / {action_target[:50]}")
    try:
        result = _run_async(_process_action_worker_async(run_id_uuid, UUID(from_node_id), action))
        _log("ACTION", run_id_uuid, f"워커 큐에서 완료: from_node={from_node_id}")
        return result
    except Exception as e:
        _log("ACTION", run_id_uuid, f"워커 큐에서 에러: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        raise


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
    action_target_short = action_target[:50] + "..." if len(action_target) > 50 else action_target
    action_value_short = (action_value[:30] + "...") if action_value and len(action_value) > 30 else (action_value or "")
    
    try:
        _log("ACTION", run_id, f"워커 시작: from_node={from_node_id}, action={action_type} / {action_target_short}")
        if action_value_short:
            _log("ACTION", run_id, f"  액션 값: {action_value_short}")
        
        # 액션 처리 락 확인 (이미 _create_action_workers에서 획득했지만, 워커 시작 시 다시 확인)
        if not acquire_action_lock(run_id, from_node_id, action_type, action_target, action_value, timeout=300):
            _log("ACTION", run_id, f"액션 처리 락 획득 실패, 종료", "WARN")
            return
        
        try:
            # 1. Playwright 페이지 생성 및 from_node_id의 URL로 이동
            _log("ACTION", run_id, f"[1/8] 시작 노드 조회 중: {from_node_id}")
            from_node = get_node_by_id(from_node_id)
            if not from_node:
                _log("ACTION", run_id, f"시작 노드를 찾을 수 없습니다: {from_node_id}", "ERROR")
                return
            
            from_node_url = from_node.get("url", "unknown")
            _log("ACTION", run_id, f"[1/8] 시작 노드 조회 완료: {from_node_url}")
            
            _log("ACTION", run_id, f"[2/8] 브라우저 컨텍스트 생성 중...")
            playwright, browser, context = await _create_browser_context()
            page = await context.new_page()
            await page.goto(from_node["url"], wait_until="networkidle")
            _log("ACTION", run_id, f"[2/8] 페이지 로드 완료: {from_node_url}")
            
            # 2. 액션 실행 및 엣지 생성 (guess_intent 포함)
            _log("ACTION", run_id, f"[3/8] 액션 실행 중: {action_type} / {action_target_short}")
            edge_service = EdgeService()
            edge = await edge_service.perform_and_record_edge(
                run_id=run_id,
                from_node_id=from_node_id,
                page=page,
                action=action
            )
            
            if not edge or edge.get("outcome") != "success":
                error_msg = edge.get('error_msg') if edge else '엣지 생성 실패'
                _log("ACTION", run_id, f"[3/8] 액션 실행 실패: {error_msg}", "ERROR")
                return
            
            edge_id = edge.get("id", "unknown")
            _log("ACTION", run_id, f"[3/8] 액션 실행 성공: 엣지 ID={edge_id}")
            
            # 3. 도착 노드 생성 (perform_and_record_edge에서 이미 생성됨)
            to_node_id = edge.get("to_node_id")
            if not to_node_id:
                _log("ACTION", run_id, f"[4/8] 도착 노드 없음", "WARN")
                return
            
            to_node_id = UUID(to_node_id)
            _log("ACTION", run_id, f"[4/8] 도착 노드 생성 완료: {to_node_id}")
            
            # 4. 도착 노드 조회 (이미 페이지가 해당 노드에 있음)
            # 5. update_run_memory_with_ai 호출 및 수정사항 확인
            _log("ACTION", run_id, f"[5/8] 스크린샷 촬영 및 run_memory 업데이트 중...")
            screenshot_bytes = await page.screenshot(type="png")
            image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            ai_service = AiService()
            updated_memory, has_changes = await ai_service.update_run_memory_with_ai(
                image_base64=image_base64,
                run_id=run_id,
                auxiliary_data=None
            )
            
            if has_changes:
                _log("ACTION", run_id, f"[5/8] run_memory 수정사항 감지됨")
            else:
                _log("ACTION", run_id, f"[5/8] run_memory 변경사항 없음")
            
            # 6. 수정사항이 있으면 process_pending_actions_worker 호출
            if has_changes:
                _log("ACTION", run_id, f"[6/8] pending actions 처리 워커 시작")
                from workers.tasks import process_pending_actions_worker
                process_pending_actions_worker.send(str(run_id))
            else:
                _log("ACTION", run_id, f"[6/8] pending actions 처리 스킵")
            
            # 7. 현재 노드에서 액션 추출 및 필터링
            _log("ACTION", run_id, f"[7/8] 액션 추출 및 필터링 중...")
            normal_actions, processable_input_actions = await _extract_and_filter_actions(
                page, run_id, to_node_id
            )
            _log("ACTION", run_id, f"[7/8] 액션 추출 완료: 일반={len(normal_actions)}, 입력={len(processable_input_actions)}")
            
            # 8. 액션 필터링 및 워커 생성
            all_processable_actions = normal_actions + processable_input_actions
            _log("ACTION", run_id, f"[8/8] 워커 생성 시작: 총 {len(all_processable_actions)}개 액션")
            await _create_action_workers(run_id, to_node_id, all_processable_actions)
            
            elapsed = time.time() - start_time
            _log("ACTION", run_id, f"워커 완료: {len(all_processable_actions)}개 액션에 대해 워커 생성 (소요시간: {elapsed:.2f}초)")
        finally:
            # 락 해제
            release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("ACTION", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        import traceback
        traceback.print_exc()
        release_action_lock(run_id, from_node_id, action_type, action_target, action_value)
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


@dramatiq.actor(max_retries=2, time_limit=300000)
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
        import traceback
        traceback.print_exc()
        raise


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
            action_target_short = action_target[:50] + "..." if len(action_target) > 50 else action_target
            
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
                    _log("PENDING", run_id, f"[2/2] [{idx}/{len(processable_actions)}] 워커 생성: {action_type} / {action_target_short} (from_node={from_node_id})")
                    matched = True
                    break
            
            if not matched:
                _log("PENDING", run_id, f"[2/2] [{idx}/{len(processable_actions)}] 매칭되는 pending action 없음: {action_type} / {action_target_short}", "WARN")
        
        elapsed = time.time() - start_time
        _log("PENDING", run_id, f"워커 완료: {created_count}개 워커 생성 (소요시간: {elapsed:.2f}초)")
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("PENDING", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        import traceback
        traceback.print_exc()
