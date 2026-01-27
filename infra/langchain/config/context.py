"""run_id / from_node_id용 context 변수. 에이전트·run_memory 툴에서 런·노드 컨텍스트 전달."""
from contextvars import ContextVar
from uuid import UUID

# run_id를 저장할 context variable
run_id_context: ContextVar[UUID | None] = ContextVar("run_id", default=None)

def set_run_id(run_id: UUID) -> None:
    """현재 context에 run_id 설정"""
    run_id_context.set(run_id)

def get_run_id() -> UUID | None:
    """현재 context에서 run_id 조회"""
    return run_id_context.get()

# from_node_id를 저장할 context variable
from_node_id_context: ContextVar[UUID | None] = ContextVar("from_node_id", default=None)

def set_from_node_id(from_node_id: UUID) -> None:
    """현재 context에 from_node_id 설정"""
    from_node_id_context.set(from_node_id)

def get_from_node_id() -> UUID | None:
    """현재 context에서 from_node_id 조회"""
    return from_node_id_context.get()