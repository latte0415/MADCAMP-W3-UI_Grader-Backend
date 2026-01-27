"""
워커 테스트 스크립트

워커가 실행 중인 상태에서 이 스크립트를 실행하여 작업을 큐에 넣고 테스트합니다.
"""

from workers.tasks import example_task, long_running_task

if __name__ == "__main__":
    print("작업을 큐에 추가합니다...")
    
    # 간단한 작업 테스트
    message_id = example_task.send("테스트 메시지")
    print(f"example_task 작업 ID: {message_id}")
    
    # 장시간 작업 테스트
    data = {"test": "data", "number": 42}
    message_id2 = long_running_task.send(data)
    print(f"long_running_task 작업 ID: {message_id2}")
    
    print("\n워커가 실행 중인 터미널에서 작업 처리 로그를 확인하세요!")
