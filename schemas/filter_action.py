"""Filter Action Chain 스키마 정의

Chain의 입력과 출력을 정의하는 Pydantic 모델
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from schemas.actions import Action, ActionType, InputType


class FilterActionInputAction(Action):
    """Filter Action Chain 입력용 액션 스키마 (Action 확장)
    
    Action의 모든 필드를 포함하되, filter action에 필요한 추가 필드를 포함합니다.
    """
    is_filled: bool = Field(
        default=False,
        description="이미 값이 채워져 있는지 여부 (true면 채울 필요 없음)"
    )
    current_value: Optional[str] = Field(
        default=None,
        description="현재 입력 필드에 채워진 값 (is_filled가 true인 경우)"
    )


class FilterActionOutputAction(Action):
    """Filter Action Chain 출력용 액션 스키마
    
    처리 가능한 액션은 action_value가 채워진 Action 형태입니다.
    원본 액션의 모든 필드를 포함하고, action_value만 적절한 값으로 채워집니다.
    """
    # action_value는 필수 (처리 가능한 액션이므로)
    # 부모 클래스의 Optional[str]을 override하여 필수로 만듦
    action_value: str = Field(
        ...,
        description="액션에 필요한 값 (fill의 경우 입력 텍스트, navigate의 경우 URL). 처리 가능한 액션은 반드시 값이 있어야 함"
    )
    
    @field_validator('input_type', mode='before')
    @classmethod
    def validate_input_type(cls, v):
        """빈 문자열을 None으로 변환하여 InputType enum 검증 통과"""
        if v == "" or v is None:
            return None
        return v
    
    model_config = {
        # 입력에만 필요한 필드(is_filled, current_value)는 출력에서 무시
        "extra": "ignore"
    }


class FilterActionInput(BaseModel):
    """Filter Action Chain 입력 스키마"""
    input_actions: List[FilterActionInputAction] = Field(
        description="입력값이 필요한 액션 리스트"
    )
    run_memory: dict = Field(
        default_factory=dict,
        description="run_memory의 content 딕셔너리"
    )


class FilterActionOutput(BaseModel):
    """Filter Action Chain 출력 스키마"""
    actions: List[FilterActionOutputAction] = Field(
        default_factory=list,
        description="처리 가능한 액션 리스트. 각 액션은 action_value가 채워진 Action 형태"
    )
