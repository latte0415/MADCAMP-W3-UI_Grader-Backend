"""
Worker Common Utilities
"""
import asyncio
import sys
from pathlib import Path
from typing import Dict, Optional, Any
from uuid import UUID

from playwright.async_api import async_playwright
from utils.logger import get_logger, set_context
from utils.action_extractor import parse_action_target

logger = get_logger(__name__)

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
