"""Run Memory Chain 스키마 정의

Chain의 출력을 정의하는 Pydantic 모델
"""

from typing import Dict, Any
from pydantic import BaseModel, Field


class UpdateRunMemoryOutput(BaseModel):
    """Update Run Memory Chain 출력 스키마"""
    content: Dict[str, Any] = Field(
        ...,
        description="업데이트할 run_memory content 딕셔너리. 전체 메모리를 포함해야 함 (기존 메모리 + 새로운 정보)"
    )
