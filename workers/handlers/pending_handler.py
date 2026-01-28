"""
Pending Action Worker Handler
"""
import time
from uuid import UUID
import dramatiq
from utils.logger import get_logger, set_context
from exceptions.worker import WorkerTaskError
from workers.handlers.common import (
    _log, 
    _check_run_status, 
)
from services.ai_service import AiService
from services.pending_action_service import PendingActionService

logger = get_logger(__name__)

async def process_pending_actions_worker_async(run_id: UUID):
    """process_pending_actions_worker의 비동기 구현"""
    from workers.tasks import process_node_worker
    
    start_time = time.time()
    
    try:
        _log("PENDING", run_id, f"워커 시작")
        
        # Run 상태 확인
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
        
        # 3. 처리 가능한 액션과 매칭하여 고유한 from_node_id 수집
        _log("PENDING", run_id, f"[2/3] pending actions 조회 중...")
        pending_action_service = PendingActionService()
        pending_actions = pending_action_service.list_pending_actions(
            run_id=run_id,
            from_node_id=None,
            status="pending"
        )
        
        _log("PENDING", run_id, f"[2/3] 전체 pending actions 수: {len(pending_actions)}")
        
        # 고유한 from_node_id 수집
        unique_node_ids = set()
        matched_actions_count = 0
        
        for idx, processable_action in enumerate(processable_actions, 1):
            if _check_run_status(run_id) is None:
                _log("PENDING", run_id, f"Run 상태 확인 실패, 작업 중단 (처리 중: {idx}/{len(processable_actions)})", "WARN")
                break
            action_type = processable_action.get("action_type", "")
            action_target = processable_action.get("action_target", "")
            
            # pending action에서 매칭되는 것 찾기
            for pending in pending_actions:
                if (pending.get("action_type") == action_type and
                    pending.get("action_target") == action_target):
                    from_node_id = UUID(pending.get("from_node_id"))
                    unique_node_ids.add(from_node_id)
                    matched_actions_count += 1
                    break
        
        _log("PENDING", run_id, f"[3/3] 매칭된 액션: {matched_actions_count}개, 고유 노드 수: {len(unique_node_ids)}개")
        
        # 4. 각 고유한 노드에 대해 process_node_worker 호출
        created_count = 0
        for from_node_id in unique_node_ids:
            if _check_run_status(run_id) is None:
                _log("PENDING", run_id, f"Run 상태 확인 실패, 작업 중단 (노드 처리 중: {created_count}/{len(unique_node_ids)})", "WARN")
                break
            process_node_worker.send(str(run_id), str(from_node_id))
            created_count += 1
            _log("PENDING", run_id, f"[3/3] [{created_count}/{len(unique_node_ids)}] 노드 워커 생성: from_node={from_node_id}")
        
        elapsed = time.time() - start_time
        _log("PENDING", run_id, f"워커 완료: {created_count}개 노드 워커 생성 (소요시간: {elapsed:.2f}초)")
        
    except Exception as e:
        elapsed = time.time() - start_time
        _log("PENDING", run_id, f"에러 발생 (소요시간: {elapsed:.2f}초): {e}", "ERROR")
        logger.error(f"pending actions 워커 에러 발생 (소요시간: {elapsed:.2f}초): {e}", exc_info=True)
