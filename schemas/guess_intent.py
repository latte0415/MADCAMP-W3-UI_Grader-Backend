"""Guess Intent Chain 스키마 정의

Chain의 출력을 정의하는 Pydantic 모델
"""

from pydantic import BaseModel, Field, field_validator


class GuessIntentOutput(BaseModel):
    """Guess Intent Chain 출력 스키마"""
    intent_label: str = Field(
        ...,
        description="엣지가 가리키는 액션의 의도를 나타내는 짧은 라벨 (15자 이내 필수, 예: 'login', 'submit_form', 'navigate_to_dashboard')"
    )
    
    @field_validator('intent_label')
    @classmethod
    def validate_intent_label(cls, v: str) -> str:
        """intent_label이 15자를 초과하면 자동으로 잘라냅니다."""
        if len(v) > 15:
            return v[:15]
        return v
