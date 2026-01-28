"""그래프 구축 완료 체크 서비스"""
import asyncio
from typing import Optional
from uuid import UUID

from repositories.edge_repository import count_success_edges_by_run_id, count_recent_success_edges_by_run_id
from repositories.run_repository import get_run_by_id, update_run
from services.analysis_service import AnalysisService
from utils.logger import get_logger, set_context, clear_context

logger = get_logger(__name__)

# 그래프 구축 설정
MAX_EDGE_COUNT = 300  # 최대 엣지 수 제한
CHECK_INTERVAL_SECONDS = 15  # 완료 체크 간격 (초)
NO_NEW_EDGES_THRESHOLD_SECONDS = 60  # 1분간 새 엣지가 없으면 완료로 간주
MIN_EDGE_COUNT_FOR_RATE_CHECK = 10  # 엣지 생성률 체크를 위한 최소 엣지 수
RECENT_EDGES_CHECK_WINDOW = 60  # 최근 N초 동안의 엣지 생성률 체크 (1분)
MIN_RECENT_EDGES_THRESHOLD = 1  # 최근 N초 동안 최소 엣지 생성 수 (너무 낮으면 완료로 간주)
LONG_NO_NEW_EDGES_THRESHOLD_SECONDS = 300  # 5분간 새 엣지가 없으면 완료로 간주 (더 긴 시간 창)


def check_graph_completion(run_id: UUID) -> bool:
    """
    그래프 구축 완료 여부를 체크합니다.
    
    완료 조건:
    1. 최대 엣지 수에 도달한 경우
    2. 일정 시간 동안 새 엣지가 생성되지 않은 경우 (추후 구현)
    
    Args:
        run_id: 탐색 세션 ID
    
    Returns:
        완료 여부
    """
    try:
        set_context(run_id=str(run_id), worker_type="GRAPH_COMPLETION_CHECKER")
        
        # Run 상태 확인
        run = get_run_by_id(run_id)
        if not run:
            logger.warning(f"Run을 찾을 수 없습니다: {run_id}")
            return False
        
        status = run.get("status")
        if status != "running":
            logger.debug(f"Run이 이미 완료되었거나 중지됨: status={status}")
            return False
        
        # 성공 엣지 개수 확인
        edge_count = count_success_edges_by_run_id(run_id)
        logger.debug(f"현재 성공 엣지 개수: {edge_count}/{MAX_EDGE_COUNT}")
        
        # 조건 1: 최대 엣지 수 체크
        if edge_count >= MAX_EDGE_COUNT:
            logger.info(f"최대 성공 엣지 수에 도달했습니다: {edge_count}/{MAX_EDGE_COUNT}")
            return True
        
        # 조건 2: 최소 엣지 수 이상인 경우에만 생성률 체크
        if edge_count >= MIN_EDGE_COUNT_FOR_RATE_CHECK:
            # 최근 N초 동안 생성된 성공 엣지 수 확인
            recent_edges = count_recent_success_edges_by_run_id(run_id, RECENT_EDGES_CHECK_WINDOW)
            logger.debug(f"최근 {RECENT_EDGES_CHECK_WINDOW}초 동안 생성된 성공 엣지 수: {recent_edges}")
            
            # 최근 N초 동안 새 성공 엣지가 거의 생성되지 않은 경우 완료로 간주
            if recent_edges < MIN_RECENT_EDGES_THRESHOLD:
                logger.info(
                    f"새 성공 엣지 생성률이 매우 낮습니다: "
                    f"최근 {RECENT_EDGES_CHECK_WINDOW}초 동안 {recent_edges}개 생성 "
                    f"(임계값: {MIN_RECENT_EDGES_THRESHOLD}개)"
                )
                return True
        
        # 조건 3: 최근 일정 시간 동안 전혀 새 성공 엣지가 생성되지 않은 경우
        # (더 긴 시간 창으로 확인)
        if edge_count > 0:  # 최소한 성공 엣지가 하나는 있어야 함
            no_new_edges_count = count_recent_success_edges_by_run_id(run_id, NO_NEW_EDGES_THRESHOLD_SECONDS)
            if no_new_edges_count == 0:
                logger.info(
                    f"최근 {NO_NEW_EDGES_THRESHOLD_SECONDS}초 동안 새 성공 엣지가 전혀 생성되지 않았습니다. "
                    f"그래프 구축이 완료된 것으로 간주합니다."
                )
                return True
        
        # 조건 4: 최근 매우 긴 시간 동안 전혀 새 성공 엣지가 생성되지 않은 경우
        # (더 안전한 장기 체크 - 엣지 생성이 완전히 멈춘 경우)
        if edge_count > 0:  # 최소한 성공 엣지가 하나는 있어야 함
            long_no_new_edges_count = count_recent_success_edges_by_run_id(run_id, LONG_NO_NEW_EDGES_THRESHOLD_SECONDS)
            if long_no_new_edges_count == 0:
                logger.info(
                    f"최근 {LONG_NO_NEW_EDGES_THRESHOLD_SECONDS}초 동안 새 성공 엣지가 전혀 생성되지 않았습니다. "
                    f"그래프 구축이 완료된 것으로 간주합니다."
                )
                return True
        
        return False
    
    except Exception as e:
        logger.error(f"그래프 완료 체크 중 오류 발생: {e}", exc_info=True)
        return False
    finally:
        clear_context()


def complete_graph_building(run_id: UUID) -> None:
    """
    그래프 구축을 완료하고 full_analysis를 시작합니다.
    
    Args:
        run_id: 탐색 세션 ID
    """
    try:
        set_context(run_id=str(run_id), worker_type="GRAPH_COMPLETION")
        
        # Run 상태 확인
        run = get_run_by_id(run_id)
        if not run:
            logger.error(f"Run을 찾을 수 없습니다: {run_id}")
            return
        
        status = run.get("status")
        if status != "running":
            logger.info(f"Run이 이미 완료되었거나 중지됨: status={status}")
            return
        
        # Run 상태를 completed로 변경
        logger.info(f"그래프 구축 완료: run_id={run_id}")
        update_run(run_id, {"status": "completed"})
        
        # 상태 변경 확인 (원자성 보장)
        run_after_update = get_run_by_id(run_id)
        if not run_after_update or run_after_update.get("status") != "completed":
            logger.error(f"Run 상태 변경 실패: run_id={run_id}")
            # 상태 변경 실패 시 failed로 변경하지 않고 로그만 남김
            # (다른 워커가 이미 상태를 변경했을 수 있음)
            return
        
        # Full analysis 워커 호출
        logger.info(f"Full analysis 워커 시작: run_id={run_id}")
        try:
            from workers.tasks import run_full_analysis_worker
            run_full_analysis_worker.send(str(run_id))
            logger.info(f"Full analysis 워커 호출 완료: run_id={run_id}")
        except Exception as worker_error:
            # 워커 호출 실패는 치명적이지 않음 (워커가 나중에 재시도할 수 있음)
            logger.warning(f"Full analysis 워커 호출 실패 (계속 진행): {worker_error}", exc_info=True)
            # 워커 호출 실패만으로는 run 상태를 failed로 변경하지 않음
            # (워커가 나중에 재시도하거나 수동으로 호출할 수 있음)
        
    except Exception as e:
        logger.error(f"그래프 구축 완료 처리 중 오류 발생: {e}", exc_info=True)
        # 완료 처리 중 오류가 발생해도 run 상태를 failed로 변경하지 않음
        # 이유:
        # 1. 상태가 이미 "completed"로 변경되었을 수 있음
        # 2. 그래프 구축은 완료되었으므로 completed 상태를 유지해야 함
        # 3. Full analysis 실행 실패는 별도로 처리됨
        try:
            # 현재 상태 확인
            run = get_run_by_id(run_id)
            current_status = run.get("status") if run else None
            logger.warning(
                f"그래프 구축 완료 처리 중 오류 발생 (run 상태는 변경하지 않음): "
                f"run_id={run_id}, 현재 상태={current_status}, 에러={str(e)[:200]}"
            )
            # 상태를 변경하지 않음 (이미 completed로 변경되었을 수 있음)
        except Exception as check_error:
            logger.error(f"Run 상태 확인 실패: {check_error}", exc_info=True)
    finally:
        clear_context()
