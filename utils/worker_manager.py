"""워커 자동 시작 관리 유틸리티"""
import os
import sys
import subprocess
import signal
import atexit
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_worker_process: Optional[subprocess.Popen] = None


def start_worker_background():
    """
    백그라운드에서 워커 프로세스를 시작합니다.
    
    환경변수 WORKER_AUTO_START가 'true'일 때만 자동 시작됩니다.
    """
    global _worker_process
    
    # 환경변수로 자동 시작 여부 제어
    auto_start = os.getenv("WORKER_AUTO_START", "false").lower() == "true"
    
    if not auto_start:
        logger.info("WORKER_AUTO_START 환경변수가 설정되지 않았습니다. 워커를 수동으로 실행하세요: python -m workers.worker")
        return
    
    if _worker_process is not None:
        logger.warning("워커 프로세스가 이미 실행 중입니다.")
        return
    
    try:
        # 프로젝트 루트 경로
        project_root = Path(__file__).parent.parent
        
        # 워커 실행 명령
        worker_command = [
            sys.executable,
            "-m",
            "workers.worker"
        ]
        
        logger.info("백그라운드 워커 프로세스 시작 중...")
        
        # 백그라운드 프로세스로 시작
        _worker_process = subprocess.Popen(
            worker_command,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy()
        )
        
        logger.info(f"워커 프로세스가 시작되었습니다. PID: {_worker_process.pid}")
        
        # 프로세스 종료 시 정리
        atexit.register(stop_worker_background)
        
    except Exception as e:
        logger.error(f"워커 프로세스 시작 실패: {e}", exc_info=True)
        _worker_process = None


def stop_worker_background():
    """백그라운드 워커 프로세스를 종료합니다."""
    global _worker_process
    
    if _worker_process is None:
        return
    
    try:
        logger.info(f"워커 프로세스 종료 중... PID: {_worker_process.pid}")
        _worker_process.terminate()
        
        # 최대 5초 대기
        try:
            _worker_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("워커 프로세스가 5초 내에 종료되지 않아 강제 종료합니다.")
            _worker_process.kill()
            _worker_process.wait()
        
        logger.info("워커 프로세스가 종료되었습니다.")
        _worker_process = None
        
    except Exception as e:
        logger.error(f"워커 프로세스 종료 실패: {e}", exc_info=True)


def is_worker_running() -> bool:
    """워커 프로세스가 실행 중인지 확인합니다."""
    global _worker_process
    
    if _worker_process is None:
        return False
    
    # 프로세스가 여전히 실행 중인지 확인
    return _worker_process.poll() is None
