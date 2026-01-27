"""액션 스키마 정의

LLM이 입력 데이터를 생성할 수 있는지 판단하고,
Playwright 워커에서 특정 노드에서 다음 액션으로 넘어갈 수 있도록
액션 정보를 표현하는 스키마입니다.
"""
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """액션 타입"""
    CLICK = "click"
    FILL = "fill"
    HOVER = "hover"
    NAVIGATE = "navigate"
    WAIT = "wait"


class InputType(str, Enum):
    """입력 필드 타입 (LLM이 적절한 값을 생성하기 위해 필요)"""
    TEXT = "text"
    EMAIL = "email"
    PASSWORD = "password"
    SEARCH = "search"
    NUMBER = "number"
    TEL = "tel"
    URL = "url"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime-local"
    UNKNOWN = "unknown"


class Action(BaseModel):
    """액션 스키마
    
    LLM이 입력 데이터를 생성할 수 있는지 판단하고,
    Playwright 워커에서 액션을 실행할 수 있도록 필요한 모든 정보를 포함합니다.
    """
    
    # 필수 필드: 액션 타입
    action_type: ActionType = Field(
        ...,
        description="액션 타입 (click, fill, hover, navigate, wait)"
    )
    
    # 요소 식별 정보 (Playwright에서 요소를 찾기 위해 필요)
    # selector가 있으면 우선 사용, 없으면 role + name 조합 사용
    selector: Optional[str] = Field(
        None,
        description="CSS selector로 요소를 식별 (우선순위 1)"
    )
    
    role: Optional[str] = Field(
        None,
        description="ARIA role (selector가 없을 때 role + name으로 요소 식별)"
    )
    
    name: Optional[str] = Field(
        None,
        description="요소 이름 (aria-label, placeholder, inner_text 등에서 추출)"
    )
    
    # 액션 타겟 (사람이 읽을 수 있는 설명)
    action_target: str = Field(
        ...,
        description="액션 타겟 설명 (예: 'role=button name=로그인')"
    )
    
    # 액션 값 (fill, navigate 등에서 필요)
    action_value: Optional[str] = Field(
        None,
        description="액션에 필요한 값 (fill의 경우 입력 텍스트, navigate의 경우 URL)"
    )
    
    # 추가 메타데이터
    tag: Optional[str] = Field(
        None,
        description="HTML 태그명 (예: 'button', 'input', 'a')"
    )
    
    href: Optional[str] = Field(
        None,
        description="링크인 경우 href 속성 (click 액션에서 URL 이동에 사용)"
    )
    
    # LLM이 입력 데이터를 생성하기 위한 정보
    input_type: Optional[InputType] = Field(
        None,
        description="입력 필드 타입 (fill 액션인 경우 LLM이 적절한 값을 생성하기 위해 필요)"
    )
    
    input_required: bool = Field(
        False,
        description="입력 값이 필수인지 여부 (LLM이 action_value를 생성해야 하는지 판단)"
    )
    
    placeholder: Optional[str] = Field(
        None,
        description="입력 필드의 placeholder (LLM이 적절한 값을 생성하는 데 참고)"
    )
    
    # 검증 메서드
    def requires_input(self) -> bool:
        """입력 값이 필요한 액션인지 확인"""
        return self.action_type == ActionType.FILL or self.input_required
    
    def can_execute(self) -> bool:
        """Playwright에서 실행 가능한지 확인 (요소 식별 정보가 있는지)"""
        if self.selector:
            return True
        if self.role and self.name:
            return True
        if self.action_type == ActionType.NAVIGATE and self.action_value:
            return True
        if self.action_type == ActionType.WAIT:
            return True
        return False
    
    def get_element_locator_info(self) -> dict:
        """Playwright에서 요소를 찾기 위한 정보 반환"""
        if self.selector:
            return {"type": "selector", "value": self.selector}
        if self.role and self.name:
            return {"type": "role", "role": self.role, "name": self.name}
        return {"type": "unknown"}
    
    def to_dict(self) -> dict:
        """Action을 딕셔너리로 변환"""
        return self.model_dump(exclude_none=False)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        """딕셔너리에서 Action 생성"""
        return cls(**data)
    
    class Config:
        use_enum_values = True
