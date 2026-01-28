"""
평가 워커 테스트 스크립트

사용법:
    python scripts/test_evaluation_worker.py <run_id>

예시:
    python scripts/test_evaluation_worker.py 667d1815-7718-40fc-bd95-c98101a11ac5
"""
import sys
from pathlib import Path
from uuid import UUID

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from workers.tasks import run_full_analysis_worker
from repositories.run_repository import get_run_by_id
from utils.logger import get_logger, setup_logging

logger = get_logger(__name__)
setup_logging("INFO")


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/test_evaluation_worker.py <run_id>")
        print("\n예시:")
        print("  python scripts/test_evaluation_worker.py 667d1815-7718-40fc-bd95-c98101a11ac5")
        sys.exit(1)
    
    run_id_str = sys.argv[1]
    
    try:
        run_id = UUID(run_id_str)
    except ValueError:
        print(f"잘못된 run_id 형식입니다: {run_id_str}")
        print("run_id는 UUID 형식이어야 합니다.")
        sys.exit(1)
    
    # Run 존재 확인
    run = get_run_by_id(run_id)
    if not run:
        print(f"Run을 찾을 수 없습니다: {run_id}")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"평가 워커 테스트")
    print(f"{'='*60}")
    print(f"Run ID: {run_id}")
    print(f"Status: {run.get('status')}")
    print(f"Target URL: {run.get('target_url')}")
    print(f"{'='*60}\n")
    
    # 평가 워커 호출
    print("평가 워커를 호출합니다...")
    try:
        message = run_full_analysis_worker.send(str(run_id))
        print(f"✅ 평가 워커가 큐에 추가되었습니다.")
        print(f"   Message ID: {message.message_id}")
        print(f"\n워커가 실행되면 로그를 확인하세요.")
        print(f"워커 실행 방법: python -m workers.worker")
    except Exception as e:
        print(f"❌ 평가 워커 호출 실패: {e}")
        logger.error(f"평가 워커 호출 실패: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
