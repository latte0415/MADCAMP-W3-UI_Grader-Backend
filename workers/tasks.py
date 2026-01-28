"""
Dramatiq 작업(actor) 정의
"""
import sys
from pathlib import Path
from uuid import UUID
from typing import Dict, Any

import dramatiq

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 로깅 시스템 초기화 (tasks 모듈 로드 시 명시적으로 초기화)
from utils.logger import setup_logging, get_logger, set_context, clear_context
setup_logging("INFO")

from workers.broker import broker
from exceptions.worker import WorkerTaskError
from workers.handlers.common import _log, _run_async

# Handlers
from workers.handlers.node_handler import process_node_worker_async, _extract_and_filter_actions
# DEPRECATED: Action worker handlers are no longer used (node-based workers are used instead)
# from workers.handlers.action_handler import _process_action_worker_async_DEPRECATED, _create_action_workers_DEPRECATED
from workers.handlers.pending_handler import process_pending_actions_worker_async

logger = get_logger(__name__)

# broker를 명시적으로 지정
dramatiq.set_broker(broker)


@dramatiq.actor
def example_task(message: str) -> str:
    """예시 작업 함수"""
    logger.info(f"처리 중: {message}")
    result = f"처리 완료: {message}"
    return result


@dramatiq.actor(max_retries=3, time_limit=60000)
def long_running_task(data: dict) -> dict:
    """장시간 실행되는 작업 예시"""
    logger.info(f"장시간 작업 시작: {data}")
    result = {"status": "completed", "data": data}
    return result


@dramatiq.actor(max_retries=2, time_limit=600000)
def process_node_worker(run_id: str, node_id: str):
    """노드를 부여받은 워커"""
    # #region agent log
    try:
        import json
        import time
        import os
        log_path = "/Users/laxogud/MADCAMP/W3/backend/.cursor/debug.log"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_entry = {
            "sessionId": "debug-session",
            "runId": "current",
            "hypothesisId": "ENTRY",
            "location": f"{__file__}:{49}",
            "message": "process_node_worker 시작",
            "data": {"run_id": run_id, "node_id": node_id},
            "timestamp": int(time.time() * 1000)
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass
    # #endregion
    run_id_uuid = UUID(run_id)
    set_context(run_id=str(run_id_uuid), worker_type="NODE")
    logger.debug(f"워커 큐에서 메시지 수신: node_id={node_id}")
    _log("NODE", run_id_uuid, f"워커 시작: node_id={node_id}", "DEBUG")
    try:
        result = _run_async(process_node_worker_async(run_id_uuid, UUID(node_id)))
        _log("NODE", run_id_uuid, f"워커 완료: node_id={node_id}", "DEBUG")
        return result
    except Exception as e:
        _log("NODE", run_id_uuid, f"워커 큐에서 에러: {e}", "ERROR")
        logger.error(f"워커 큐에서 에러 발생: {e}", exc_info=True)
        raise WorkerTaskError("process_node", run_id=run_id, original_error=e)


# DEPRECATED: 더미 actor - 큐에 남아있는 메시지를 처리하기 위해 유지
# 실제로는 작동하지 않으며, 경고만 출력하고 종료
@dramatiq.actor(max_retries=0, time_limit=1000)
def process_action_worker(run_id: str, from_node_id: str, action: Dict[str, Any]):
    """[DEPRECATED - DISABLED] 액션을 부여받은 워커 - 노드 기준 워커로 대체됨
    
    이 actor는 큐에 남아있는 메시지를 처리하기 위한 더미입니다.
    실제 작업은 수행하지 않으며, 경고만 출력하고 종료합니다.
    """
    logger.warning(
        f"⚠ DEPRECATED: process_action_worker 호출됨 (비활성화됨) - "
        f"run_id={run_id}, from_node_id={from_node_id}. "
        f"이 메시지는 무시됩니다. 노드 기준 워커(process_node_worker)를 사용하세요."
    )
    _log("ACTION", UUID(run_id), f"DEPRECATED actor 호출됨 - 무시됨", "WARN")
    # 메시지를 무시하고 성공으로 처리 (재시도 방지)
    return {"status": "ignored", "reason": "DEPRECATED - use process_node_worker instead"}


# DEPRECATED: 이 함수는 더 이상 사용되지 않음 (위의 actor로 대체됨)
def process_action_worker_DEPRECATED(run_id: str, from_node_id: str, action: Dict[str, Any]):
    """[DEPRECATED - DISABLED] 액션을 부여받은 워커 - 노드 기준 워커로 대체됨"""
    logger.warning(f"process_action_worker_DEPRECATED 호출됨 (비활성화됨): run_id={run_id}, from_node_id={from_node_id}")
    raise WorkerTaskError(
        "process_action_DEPRECATED", 
        run_id=run_id, 
        original_error=Exception("DEPRECATED: process_action_worker is disabled. Use process_node_worker instead.")
    )


@dramatiq.actor(max_retries=2, time_limit=600000)
def process_pending_actions_worker(run_id: str):
    """pending actions 처리 워커"""
    run_id_uuid = UUID(run_id)
    _log("PENDING", run_id_uuid, f"워커 큐에서 시작됨")
    try:
        result = _run_async(process_pending_actions_worker_async(run_id_uuid))
        _log("PENDING", run_id_uuid, f"워커 큐에서 완료")
        return result
    except Exception as e:
        _log("PENDING", run_id_uuid, f"워커 큐에서 에러: {e}", "ERROR")
        logger.error(f"워커 큐에서 에러 발생: {e}", exc_info=True)
        raise WorkerTaskError("process_pending_actions", run_id=run_id, original_error=e)

# Graph Completion Checker Worker and Helper (Kept here or could be moved)
# Since check_graph_completion_worker was in tasks.py, we keep it here but could move logic to handlers.
# For simplicity, we keep the logic here as it's relatively small compared to others, or move it to completion_handler.
# The user prompt was about tasks.py being too big.
# I'll keep it here for now to minimize changes, as it was at the end of the file.

@dramatiq.actor(max_retries=2, time_limit=600000)
def check_graph_completion_worker(run_id: str):
    """그래프 구축 완료 여부를 체크하는 워커"""
    run_id_uuid = UUID(run_id)
    set_context(run_id=str(run_id_uuid), worker_type="GRAPH_COMPLETION_CHECKER")
    logger.debug(f"그래프 완료 체크 워커 시작: run_id={run_id}")
    
    from utils.lock_manager import acquire_completion_check_lock, release_completion_check_lock
    
    lock_acquired = acquire_completion_check_lock(
        run_id_uuid,
        timeout=30,
        retry_interval=0.1,
        max_retries=0
    )
    
    if not lock_acquired:
        logger.debug(f"그래프 완료 체크 워커 스킵 (다른 워커가 실행 중): run_id={run_id}")
        clear_context()
        return
    
    try:
        from services.graph_completion_service import check_graph_completion, complete_graph_building, CHECK_INTERVAL_SECONDS
        from repositories.run_repository import get_run_by_id
        
        run = get_run_by_id(run_id_uuid)
        if not run:
            logger.warning(f"Run을 찾을 수 없습니다: {run_id}")
            return
        
        status = run.get("status")
        if status != "running":
            logger.debug(f"Run이 이미 완료되었거나 중지됨: status={status}, 재스케줄링하지 않음")
            return
        
        is_complete = check_graph_completion(run_id_uuid)
        
        if is_complete:
            logger.info(f"그래프 구축 완료 감지: run_id={run_id}")
            complete_graph_building(run_id_uuid)
        else:
            logger.debug(f"그래프 구축 진행 중: run_id={run_id}, {CHECK_INTERVAL_SECONDS}초 후 재체크 예약")
            check_graph_completion_worker.send_with_options(
                args=(run_id,),
                delay=CHECK_INTERVAL_SECONDS * 1000
            )
    
    except Exception as e:
        logger.error(f"그래프 완료 체크 워커 에러 발생: {e}", exc_info=True)
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
        release_completion_check_lock(run_id_uuid)
        clear_context()


@dramatiq.actor(max_retries=0, time_limit=300000)
def periodic_completion_check_worker():
    """주기적으로 모든 running 상태의 run을 체크하는 워커"""
    from repositories.run_repository import get_runs_by_status
    from services.graph_completion_service import CHECK_INTERVAL_SECONDS
    
    set_context(worker_type="PERIODIC_COMPLETION_CHECKER")
    logger.info("정기적 그래프 완료 체크 시작")
    
    try:
        running_runs = get_runs_by_status("running")
        logger.info(f"체크 대상 Run 수: {len(running_runs)}")
        
        for run in running_runs:
            run_id = str(run["id"])
            check_graph_completion_worker.send(run_id)
        
        # 다음 주기적 체크 예약
        logger.debug(f"다음 주기적 체크 예약: {CHECK_INTERVAL_SECONDS}초 후")
        periodic_completion_check_worker.send_with_options(
            args=(),
            delay=CHECK_INTERVAL_SECONDS * 1000
        )
            
    except Exception as e:
        logger.error(f"정기적 그래프 완료 체크 중 에러: {e}", exc_info=True)
        # 에러 발생 시에도 다음 체크 예약 (워커가 계속 실행되도록)
        try:
            periodic_completion_check_worker.send_with_options(
                args=(),
                delay=CHECK_INTERVAL_SECONDS * 1000
            )
        except Exception as reschedule_error:
            logger.error(f"재스케줄링 실패: {reschedule_error}", exc_info=True)
    finally:
        clear_context()


@dramatiq.actor(max_retries=1, time_limit=1800000)  # 30분 타임아웃
def run_full_analysis_worker(run_id: str):
    """전체 분석(평가)을 실행하는 워커"""
    run_id_uuid = UUID(run_id)
    set_context(run_id=str(run_id_uuid), worker_type="FULL_ANALYSIS")
    logger.info(f"전체 분석 워커 시작: run_id={run_id}")
    
    try:
        from services.analysis_service import AnalysisService
        from repositories.run_repository import get_run_by_id, update_run
        from routers.evaluation import _save_analysis_results_to_db
        
        # Run 존재 확인
        run = get_run_by_id(run_id_uuid)
        if not run:
            logger.error(f"Run을 찾을 수 없습니다: {run_id}")
            raise WorkerTaskError("run_full_analysis", run_id=run_id, original_error=Exception(f"Run not found: {run_id}"))
        
        status = run.get("status")
        if status != "completed":
            logger.warning(f"Run 상태가 completed가 아닙니다: status={status}, 평가를 진행합니다.")
        
        # 전체 분석 실행
        logger.info(f"전체 분석 실행 시작: run_id={run_id}")
        analysis_result = AnalysisService.run_full_analysis(run_id_uuid)
        
        if not analysis_result:
            logger.error(f"전체 분석 결과가 없습니다: run_id={run_id}")
            raise WorkerTaskError("run_full_analysis", run_id=run_id, original_error=Exception("Analysis result is None"))
        
        # 결과를 DB에 저장
        logger.info(f"분석 결과를 DB에 저장 중: run_id={run_id}")
        _save_analysis_results_to_db(run_id_uuid, analysis_result)
        
        logger.info(f"전체 분석 워커 완료: run_id={run_id}")
        return {"status": "completed", "run_id": run_id}
        
    except Exception as e:
        _log("FULL_ANALYSIS", run_id_uuid, f"워커 에러: {e}", "ERROR")
        logger.error(f"전체 분석 워커 에러 발생: {e}", exc_info=True)
        raise WorkerTaskError("run_full_analysis", run_id=run_id, original_error=e)
    finally:
        clear_context()
