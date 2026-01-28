"""모니터링 API 라우터"""
from typing import Dict, Any
from uuid import UUID
from fastapi import APIRouter, HTTPException
from datetime import datetime

from repositories.run_repository import get_run_by_id
from repositories.node_repository import get_nodes_by_run_id
from repositories.edge_repository import get_edges_by_run_id
from repositories.ai_memory_repository import get_run_memory, get_pending_actions_by_run_id
from services.worker_monitor_service import WorkerMonitorService

router = APIRouter(prefix="/api", tags=["monitor"])


@router.get("/runs/{run_id}/monitor")
async def get_run_monitor(run_id: UUID) -> Dict[str, Any]:
    """
    run_id에 대한 모니터링 통계 데이터 조회
    
    Returns:
        - run_info: Run 기본 정보
        - statistics: 노드/엣지 통계
        - pending_actions: Pending actions 수
        - run_memory: Run memory 상태
    """
    # Run 정보 조회
    run = get_run_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run을 찾을 수 없습니다: {run_id}")
    
    # 노드/엣지 조회
    nodes = get_nodes_by_run_id(run_id)
    edges = get_edges_by_run_id(run_id)
    
    # 통계 계산
    node_count = len(nodes)
    edge_count = len(edges)
    
    # 액션 타입별 분포
    action_type_distribution = {}
    success_count = 0
    fail_count = 0
    
    for edge in edges:
        action_type = edge.get("action_type", "unknown")
        action_type_distribution[action_type] = action_type_distribution.get(action_type, 0) + 1
        
        outcome = edge.get("outcome", "unknown")
        if outcome == "success":
            success_count += 1
        elif outcome in ["fail", "timeout", "blocked"]:
            fail_count += 1
    
    # Pending actions 조회
    pending_actions = get_pending_actions_by_run_id(run_id, status="pending")
    pending_count = len(pending_actions)
    
    # Run memory 조회
    run_memory = get_run_memory(run_id)
    memory_content = run_memory.get("content", {}) if run_memory else {}
    memory_key_count = len(memory_content) if isinstance(memory_content, dict) else 0
    
    # 실행 시간 계산
    created_at = run.get("created_at")
    completed_at = run.get("completed_at")
    elapsed_time = None
    if created_at:
        try:
            # ISO 형식 문자열을 datetime으로 변환
            if isinstance(created_at, str):
                if created_at.endswith("Z"):
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                else:
                    created_dt = datetime.fromisoformat(created_at)
            else:
                created_dt = created_at
            
            if completed_at:
                # 완료된 경우
                if isinstance(completed_at, str):
                    if completed_at.endswith("Z"):
                        completed_dt = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                    else:
                        completed_dt = datetime.fromisoformat(completed_at)
                else:
                    completed_dt = completed_at
                elapsed_time = (completed_dt - created_dt).total_seconds()
            else:
                # 진행 중인 경우
                elapsed_time = (datetime.now(created_dt.tzinfo) - created_dt).total_seconds()
        except (ValueError, AttributeError) as e:
            from utils.logger import get_logger
            logger = get_logger(__name__)
            logger.warning(f"시간 계산 실패: {e}", exc_info=True)
            elapsed_time = None
    
    # Pending actions 포맷팅 (type 또는 action_type 필드 보장)
    formatted_pending_actions = []
    for action in pending_actions[:10]:  # 최대 10개만 반환
        formatted_action = dict(action)
        # type 필드가 없으면 action_type을 type으로도 추가
        if "type" not in formatted_action and "action_type" in formatted_action:
            formatted_action["type"] = formatted_action["action_type"]
        formatted_pending_actions.append(formatted_action)
    
    # Run memory 포맷팅
    run_memory_response = {}
    if run_memory and memory_content:
        run_memory_response["key_count"] = memory_key_count
        run_memory_response["memory"] = memory_content
        # data 필드도 추가 (스펙에서 지원)
        run_memory_response["data"] = memory_content
    elif run_memory:
        # content가 비어있거나 None인 경우
        run_memory_response["key_count"] = 0
        run_memory_response["memory"] = {}
        run_memory_response["data"] = {}
    else:
        # run_memory가 없는 경우
        run_memory_response["key_count"] = 0
        run_memory_response["memory"] = {}
        run_memory_response["data"] = {}
    
    return {
        "run_info": {
            "run_id": str(run_id),
            "status": run.get("status"),
            "target_url": run.get("target_url"),
            "start_url": run.get("start_url"),
            "created_at": created_at,
            "completed_at": completed_at,
            "execution_time": elapsed_time
        },
        "statistics": {
            "node_count": node_count,
            "edge_count": edge_count,
            "action_type_distribution": action_type_distribution,
            "edge_outcomes": {
                "success": success_count,
                "fail": fail_count,
                "total": edge_count
            }
        },
        "pending_actions": {
            "count": pending_count,
            "actions": formatted_pending_actions
        },
        "run_memory": run_memory_response
    }


@router.get("/runs/{run_id}/graph")
async def get_run_graph(run_id: UUID) -> Dict[str, Any]:
    """
    run_id에 대한 그래프 구조 데이터 조회
    
    Returns:
        - nodes: 노드 리스트
        - edges: 엣지 리스트
    """
    # Run 존재 확인
    run = get_run_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run을 찾을 수 없습니다: {run_id}")
    
    # 노드/엣지 조회
    nodes = get_nodes_by_run_id(run_id)
    edges = get_edges_by_run_id(run_id)
    
    # 필요한 필드만 추출
    node_list = []
    for node in nodes:
        node_list.append({
            "id": node.get("id"),
            "url": node.get("url"),
            "url_normalized": node.get("url_normalized"),
            "created_at": node.get("created_at")
        })
    
    edge_list = []
    for edge in edges:
        outcome = edge.get("outcome", "unknown")
        success = outcome == "success"
        
        edge_list.append({
            "id": edge.get("id"),
            "source": edge.get("from_node_id"),
            "target": edge.get("to_node_id"),
            "action_type": edge.get("action_type"),
            "success": success,
            "action_target": edge.get("action_target"),
            "action_value": edge.get("action_value"),
            "intent_label": edge.get("intent_label"),
            "outcome": outcome,
            "created_at": edge.get("created_at")
        })
    
    return {
        "nodes": node_list,
        "edges": edge_list
    }


@router.get("/workers/status")
async def get_workers_status() -> Dict[str, Any]:
    """
    전체 워커 상태 조회
    
    Returns:
        모든 워커의 상태 정보
    """
    monitor_service = WorkerMonitorService()
    return monitor_service.get_all_workers_status()


@router.get("/workers/status/{run_id}")
async def get_run_workers_status(run_id: UUID) -> Dict[str, Any]:
    """
    특정 run_id와 관련된 워커 상태 조회
    
    Returns:
        run_id 관련 워커 상태 정보
    """
    # Run 존재 확인
    run = get_run_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run을 찾을 수 없습니다: {run_id}")
    
    monitor_service = WorkerMonitorService()
    return monitor_service.get_run_worker_status(run_id)
