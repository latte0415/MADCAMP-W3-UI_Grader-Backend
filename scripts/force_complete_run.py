#!/usr/bin/env python3
"""run_id를 입력받아 강제로 완료 처리하고 full_analysis를 시작하는 스크립트"""
import sys
from uuid import UUID
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from repositories.run_repository import get_run_by_id, update_run
from services.graph_completion_service import complete_graph_building
from utils.logger import get_logger, setup_logging

# 로깅 설정
setup_logging("INFO")
logger = get_logger(__name__)


def force_complete_run(run_id: UUID, skip_analysis: bool = False) -> bool:
    """
    run을 강제로 완료 처리하고 full_analysis를 시작합니다.
    
    Args:
        run_id: 완료 처리할 run ID
        skip_analysis: True면 분석을 건너뛰고 상태만 변경
    
    Returns:
        성공 여부
    """
    try:
        # Run 조회
        logger.info(f"Run 조회 중: {run_id}")
        run = get_run_by_id(run_id)
        
        if not run:
            logger.error(f"❌ Run을 찾을 수 없습니다: {run_id}")
            return False
        
        current_status = run.get("status")
        logger.info(f"현재 Run 상태: {current_status}")
        
        # 이미 완료된 경우
        if current_status in ["completed", "failed", "stopped"]:
            logger.warning(f"⚠️  Run이 이미 {current_status} 상태입니다.")
            if current_status == "completed":
                logger.info("✅ Run이 이미 완료되어 있습니다.")
                return True
            else:
                response = input(f"Run이 {current_status} 상태입니다. 강제로 completed로 변경하고 분석을 시작하시겠습니까? (y/N): ")
                if response.lower() != 'y':
                    logger.info("취소되었습니다.")
                    return False
        
        # 완료 처리
        if skip_analysis:
            logger.info(f"Run 상태를 completed로 변경 중... (분석 건너뜀)")
            update_run(run_id, {
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat() + "Z"
            })
            logger.info("✅ Run 상태를 completed로 변경했습니다.")
        else:
            logger.info(f"그래프 구축 완료 처리 및 full_analysis 시작 중...")
            complete_graph_building(run_id)
            logger.info("✅ Run 완료 처리 및 full_analysis 워커 시작 완료")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Run 완료 처리 중 오류 발생: {e}", exc_info=True)
        return False


def main():
    """메인 함수"""
    if len(sys.argv) < 2:
        print("사용법: python force_complete_run.py <run_id> [--skip-analysis]")
        print("예시: python force_complete_run.py 38e1e849-0e66-4635-a13b-fda339e95b07")
        print("예시: python force_complete_run.py 38e1e849-0e66-4635-a13b-fda339e95b07 --skip-analysis")
        print("\n옵션:")
        print("  --skip-analysis: 상태만 변경하고 full_analysis는 시작하지 않음")
        sys.exit(1)
    
    run_id_str = sys.argv[1]
    # skip_analysis = "--skip-analysis" in sys.argv
    skip_analysis = False
    
    try:
        run_id = UUID(run_id_str)
    except ValueError:
        print(f"❌ 잘못된 UUID 형식: {run_id_str}")
        sys.exit(1)
    
    # 완료 처리
    try:
        success = force_complete_run(run_id, skip_analysis=skip_analysis)
        if success:
            print(f"\n✅ 완료 처리 성공: {run_id}")
            if not skip_analysis:
                print("   full_analysis 워커가 시작되었습니다.")
        else:
            print(f"\n❌ 완료 처리 실패: {run_id}")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 취소되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"스크립트 실행 중 오류 발생: {e}", exc_info=True)
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
