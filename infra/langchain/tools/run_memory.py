"""run_memory·filter-action 툴 (view_memory, update_memory, save_action, final_response)."""
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
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
    href: Optional[str] = Field(default="", description="링크 href")
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
    현재 기억으로 도저히 처리할 수 없는 Input 액션을 pending_action에 보관합니다.
    
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


class FinalResponse(BaseModel):
    """처리 가능한 액션 리스트 (최종 답변용). """
    actions: List[Dict[str, Any]] = Field(
        description="처리 가능한 액션 리스트. 각 액션은 action_value가 채워진 딕셔너리 형태여야 합니다. 없을 경우, 빈 리스트를 반환해도 됩니다. 사용하자마자 종료할 것."
    )


@tool(args_schema=FinalResponse)
def final_response(actions: List[Dict[str, Any]]) -> dict:
    """
    처리 가능한 Input 액션만 입력값과 함께 최종 답변으로 반환합니다.
    
    이 도구는 반드시 최종에 한 번만 사용해야 합니다. 모든 액션을 검토한 후,
    처리 가능한 액션만 이 도구로 최종 답변으로 반환합니다.
    
    중요: 각 액션은 원본 액션의 모든 필드를 포함해야 합니다:
        - action_type: 액션 타입 (필수)
        - action_target: 액션 타겟 (필수)
        - action_value: 액션 값 (fill 액션의 경우 필수, 적절한 값으로 채워야 함)
        - role: ARIA role (요소 식별에 필요)
        - name: 요소 이름 (요소 식별에 필요)
        - selector: CSS selector (요소 식별에 필요)
        - 기타 원본 액션의 모든 필드
    
    Args:
        actions: 처리 가능한 액션 리스트. 각 액션은 원본 액션의 모든 필드를 포함하고,
                action_value만 적절한 값으로 채워서 반환해야 합니다.
    
    Returns:
        {"actions": [...]} 형태의 딕셔너리
    """
    print(f"[FinalResponse] 처리 가능한 액션 {len(actions)}개 반환")
    # 디버깅: 첫 번째 액션의 필드 확인
    if actions:
        first_action = actions[0]
        print(f"[FinalResponse] 첫 번째 액션 필드: role={first_action.get('role')}, name={first_action.get('name')}, selector={first_action.get('selector')}")
    return {"actions": actions}


update_run_memory_tools = [view_memory, update_memory]
filter_action_tools = [view_memory, save_action, final_response]