from langchain_core.tools import tool
from infra.langchain.config.context import get_run_id
from repositories.ai_memory_repository import (
    view_run_memory, update_run_memory
)

@tool
def view_memory() -> dict:
    """
    현재 run_id의 메모리를 조회합니다.
    
    Returns:
        현재 run_memory의 content 딕셔너리. 없으면 빈 딕셔너리 {}를 반환합니다.
        예: {"login_page": "로그인 페이지에는 이메일과 비밀번호 입력 필드가 있음", "생성한 ID": "예시 ID 기입"}
    """
    run_id = get_run_id()
    if not run_id:
        return {"error": "run_id가 설정되지 않았습니다."}
    result = view_run_memory(run_id)
    if result and "content" in result:
        return result["content"]
    return {}

@tool
def update_memory(content: dict) -> dict:
    """
    현재 run_id의 메모리를 업데이트합니다.
    
    중요: 이 도구는 전체 메모리를 교체합니다. 기존 메모리를 유지하려면 먼저 view_memory()를 호출하여
    현재 메모리를 가져온 후, 새로운 정보를 추가하여 전체 딕셔너리를 전달해야 합니다.
    
    Args:
        content: 업데이트할 메모리 내용 딕셔너리. 
                 예: {"login_page": "로그인 페이지에는 이메일과 비밀번호 입력 필드가 있음", 
                      "생성한 ID": "예시 ID 기입"}
                 
    Returns:
        업데이트된 run_memory 정보 딕셔너리
        
    사용 예시:
        1. 먼저 view_memory()를 호출하여 현재 메모리를 확인
        2. 새로운 정보를 기존 메모리에 추가
        3. update_memory(전체_메모리_딕셔너리)를 호출
    """
    run_id = get_run_id()
    if not run_id:
        return {"error": "run_id가 설정되지 않았습니다."}
    if not content or not isinstance(content, dict):
        return {"error": "content는 비어있지 않은 딕셔너리여야 합니다."}
    return update_run_memory(run_id, content)

update_run_memory_tools = [view_memory, update_memory]