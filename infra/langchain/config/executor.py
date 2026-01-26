import asyncio
import time
from typing import Any
from langchain_core.runnables import Runnable
from langchain_core.exceptions import OutputParserException

MAX_RETRIES = 3
DELAY = 1  # 재시도 간 대기 시간 (초)


async def ainvoke_runnable(
    runnable: Runnable,
    variables: dict[str, Any],
    step_label: str = "",
    config: dict[str, Any] | None = None,
) -> Any:
    """
    Runnable을 비동기적으로 실행하며, 재시도 옵션을 지원합니다.
    Infrastructure 레이어: 에러 발생 시 RuntimeError를 발생시킵니다.

    Args:
        runnable: 실행할 LangChain Runnable 객체
        variables: Runnable에 전달할 입력 변수
        step_label: 단계 레이블 (에러 메시지용)
        config: 실행 설정 (timeout 등)

    Returns:
        Runnable 실행 결과

    Raises:
        RuntimeError: 실행 실패 시
    """
    last_error = None
    start = time.time()

    merged_config = {"timeout": 30, **(config or {})}

    for attempt in range(MAX_RETRIES):
        try:
            response = await runnable.ainvoke(variables, config=merged_config)
            return response
        except OutputParserException as e:
            # OutputParserException은 LLM 응답 파싱 실패를 의미
            llm_output = getattr(e, 'llm_output', 'N/A')
            error_msg = (
                f"[{step_label}] LLM 응답 파싱 실패 (시도 {attempt + 1}/{MAX_RETRIES}):\n"
                f"  에러: {e}\n"
                f"  LLM 원본 출력: {llm_output}\n"
                f"  원인: LLM이 유효한 JSON 형식으로 응답하지 않았습니다."
            )
            last_error = error_msg
            print(error_msg)
            # OutputParserException은 재시도해도 같은 문제가 발생할 가능성이 높으므로 즉시 실패 처리
            raise RuntimeError(error_msg) from e
        except Exception as e:
            last_error = f"[{step_label}] invoke 에러 (시도 {attempt + 1}/{MAX_RETRIES}): {e!s}"
            print(last_error)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(DELAY)
    
    # 모든 재시도 실패 시 RuntimeError 발생
    raise RuntimeError(last_error or f"[{step_label}] 체인 실행 실패")