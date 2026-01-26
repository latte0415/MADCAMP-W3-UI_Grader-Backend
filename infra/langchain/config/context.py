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