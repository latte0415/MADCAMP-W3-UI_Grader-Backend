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
from repositories.site_evaluation_repository import get_site_evaluation_by_run_id
from utils.logger import get_logger, setup_logging
import time

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
    
    # 기존 평가 결과 확인
    existing_evaluation = get_site_evaluation_by_run_id(run_id)
    if existing_evaluation:
        print(f"⚠️  이미 평가 결과가 존재합니다:")
        print(f"   Total Score: {existing_evaluation.get('total_score', 'N/A')}")
        print(f"   Created At: {existing_evaluation.get('created_at', 'N/A')}")
        response = input("\n새로 평가를 실행하시겠습니까? (y/N): ")
        if response.lower() != 'y':
            print("취소되었습니다.")
            sys.exit(0)
    
    # 평가 워커 호출
    print("\n평가 워커를 호출합니다...")
    try:
        message = run_full_analysis_worker.send(str(run_id))
        print(f"✅ 평가 워커가 큐에 추가되었습니다.")
        print(f"   Message ID: {message.message_id}")
        print(f"\n{'='*60}")
        print("워커 실행 확인:")
        print(f"{'='*60}")
        print("1. 워커가 실행 중인지 확인:")
        print("   python -m workers.worker")
        print("\n2. 평가 결과 확인 (몇 분 후):")
        print(f"   python scripts/test_evaluation_worker.py {run_id} --check")
        print(f"\n또는 API로 확인:")
        print(f"   GET /api/evaluation/{run_id}")
    except Exception as e:
        print(f"❌ 평가 워커 호출 실패: {e}")
        logger.error(f"평가 워커 호출 실패: {e}", exc_info=True)
        sys.exit(1)
    
    # --check 옵션이 있으면 결과 확인
    if len(sys.argv) > 2 and sys.argv[2] == "--check":
        print(f"\n{'='*60}")
        print("평가 결과 확인 중...")
        print(f"{'='*60}")
        
        max_wait = 300  # 최대 5분 대기
        check_interval = 5  # 5초마다 확인
        waited = 0
        
        while waited < max_wait:
            evaluation = get_site_evaluation_by_run_id(run_id)
            if evaluation:
                print(f"\n✅ 평가 완료!")
                print(f"   Total Score: {evaluation.get('total_score', 'N/A')}")
                print(f"   Learnability: {evaluation.get('learnability_score', 'N/A')}")
                print(f"   Efficiency: {evaluation.get('efficiency_score', 'N/A')}")
                print(f"   Control: {evaluation.get('control_score', 'N/A')}")
                print(f"   Created At: {evaluation.get('created_at', 'N/A')}")
                sys.exit(0)
            
            print(f"   대기 중... ({waited}초 / {max_wait}초)")
            time.sleep(check_interval)
            waited += check_interval
        
        print(f"\n⚠️  평가가 아직 완료되지 않았습니다.")
        print(f"   워커가 실행 중인지 확인하세요: python -m workers.worker")
        print(f"   또는 나중에 다시 확인: python scripts/test_evaluation_worker.py {run_id} --check")


if __name__ == "__main__":
    main()
