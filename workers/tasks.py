"""
Dramatiq 작업(actor) 정의

@dramatiq.actor 데코레이터를 사용하여 비동기 작업을 정의합니다.
"""

import dramatiq
from workers.broker import broker

# broker를 명시적으로 지정
dramatiq.set_broker(broker)


@dramatiq.actor
def example_task(message: str) -> str:
    """
    예시 작업 함수
    
    Args:
        message: 처리할 메시지
        
    Returns:
        처리 결과 문자열
    """
    print(f"[Worker] 처리 중: {message}")
    result = f"처리 완료: {message}"
    return result


@dramatiq.actor(max_retries=3, time_limit=60000)
def long_running_task(data: dict) -> dict:
    """
    장시간 실행되는 작업 예시
    
    Args:
        data: 처리할 데이터 딕셔너리
        
    Returns:
        처리 결과 딕셔너리
    """
    print(f"[Worker] 장시간 작업 시작: {data}")
    # 실제 작업 로직은 여기에 구현
    result = {"status": "completed", "data": data}
    return result
