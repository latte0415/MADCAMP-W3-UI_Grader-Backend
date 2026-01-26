from langchain_core.tools import tool
from pydantic import BaseModel, Field

class FinalResponse(BaseModel):
    """계산 최종 결과를 반환합니다."""
    response: int = Field(description="계산의 최종 결과값 (정수)")


@tool
def add(a: float, b: float) -> float:
    """
    두 숫자의 합을 반환합니다.
    Args:
        a (float): 첫 번째 숫자.
        b (float): 두 번째 숫자.
    """
    print(f"Adding {a} and {b} = {a + b}")
    return a + b


@tool
def subtract(a: float, b: float) -> float:
    """
    두 숫자의 차를 반환합니다.
    Args:
        a (float): 첫 번째 숫자.
        b (float): 두 번째 숫자.
    """
    print(f"Subtracting {b} from {a} = {a - b}")
    return a - b


@tool(args_schema=FinalResponse)
def final_response(response: int) -> dict:
    """
    계산이 완료되면 반드시 이 도구를 호출하여 최종 답변을 제출하세요.
    모든 계산이 끝난 후, 최종 결과값을 이 도구로 전달해야 합니다.
    
    Args:
        response: 계산의 최종 결과값 (정수)
    
    Returns:
        최종 답변 딕셔너리 {"response": int}
    """
    print(f"[FinalResponse] 최종 답변: {response}")
    return {"response": response}


calculator_tools = [add, subtract, final_response]
