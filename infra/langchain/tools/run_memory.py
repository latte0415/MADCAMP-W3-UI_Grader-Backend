"""run_memory·filter-action 툴 (view_memory, update_memory, save_action, filter_action)."""
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from infra.langchain.config.context import get_run_id, get_from_node_id
from repositories.ai_memory_repository import (
    view_run_memory, update_run_memory, create_pending_action
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

class ActionDict(BaseModel):
    """액션 딕셔너리 스키마 (save_action 툴용)"""
    action_type: str = Field(description="액션 타입 (click, fill, hover, navigate, wait)")
    action_target: str = Field(description="액션 타겟 설명")
    action_value: str = Field(default="", description="액션 값 (fill의 경우 입력 텍스트)")
    selector: str = Field(default="", description="CSS selector")
    role: str = Field(default="", description="ARIA role")
    name: str = Field(default="", description="요소 이름")
    tag: str = Field(default="", description="HTML 태그명")
    href: str = Field(default="", description="링크 href")
    input_type: str = Field(default="", description="입력 필드 타입")
    placeholder: str = Field(default="", description="placeholder")


@tool(args_schema=ActionDict)
def save_action(
    action_type: str,
    action_target: str,
    action_value: str = "",
    selector: str = "",
    role: str = "",
    name: str = "",
    tag: str = "",
    href: str = "",
    input_type: str = "",
    placeholder: str = ""
) -> dict:
    """
    현재 처리할 수 없는 Input 액션을 pending_action에 보관합니다.
    
    LLM이 현재 메모리나 컨텍스트로는 적절한 입력값을 생성할 수 없는 액션을
    나중에 처리하기 위해 pending_action에 저장합니다.
    
    Args:
        action_type: 액션 타입 (click, fill, hover, navigate, wait)
        action_target: 액션 타겟 설명
        action_value: 액션 값 (기본값: 빈 문자열)
        selector: CSS selector (선택적)
        role: ARIA role (선택적)
        name: 요소 이름 (선택적)
        tag: HTML 태그명 (선택적)
        href: 링크 href (선택적)
        input_type: 입력 필드 타입 (선택적)
        placeholder: placeholder (선택적)
    
    Returns:
        생성된 pending_action 정보 딕셔너리
    """
    run_id = get_run_id()
    if not run_id:
        return {"error": "run_id가 설정되지 않았습니다."}
    
    from_node_id = get_from_node_id()
    if not from_node_id:
        return {"error": "from_node_id가 설정되지 않았습니다."}
    
    try:
        pending_action = create_pending_action(
            run_id=run_id,
            from_node_id=from_node_id,
            action_type=action_type,
            action_target=action_target,
            action_value=action_value or "",
            status="pending"
        )
        return {
            "success": True,
            "pending_action_id": pending_action["id"],
            "message": f"액션이 pending_action에 저장되었습니다: {action_target}"
        }
    except Exception as e:
        return {"error": f"pending_action 저장 실패: {str(e)}"}


class FilteredActions(BaseModel):
    """처리 가능한 액션 리스트 (filter_action 툴용)"""
    actions: List[Dict[str, Any]] = Field(
        description="처리 가능한 액션 리스트. 각 액션은 action_value가 채워진 딕셔너리 형태여야 합니다."
    )


@tool(args_schema=FilteredActions)
def filter_action(actions: List[Dict[str, Any]]) -> dict:
    """
    현재 처리할 수 있는 Input 액션만 입력값과 함께 반환합니다.
    
    이 도구는 반드시 최종에만 사용해야 합니다. LLM이 view_memory와 save_action을 사용하여
    처리할 수 없는 액션을 pending_action에 저장한 후, 처리 가능한 액션만 이 도구로 반환합니다.
    
    Args:
        actions: 처리 가능한 액션 리스트. 각 액션은 다음 필드를 포함해야 합니다:
            - action_type: 액션 타입 (필수)
            - action_target: 액션 타겟 (필수)
            - action_value: 액션 값 (fill 액션의 경우 필수)
            - selector, role, name 등 기타 필드 (선택적)
    
    Returns:
        {"actions": [...]} 형태의 딕셔너리
    """
    print(f"[FilterAction] 처리 가능한 액션 {len(actions)}개 반환")
    return {"actions": actions}


update_run_memory_tools = [view_memory, update_memory]
filter_action_tools = [view_memory, save_action, filter_action]