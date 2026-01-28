"""Full Analysis Orchestrator (하위 호환용 wrapper)
한 개의 Run에 대해 정적 분석(Node), 전이 분석(Edge), 워크플로우 분석(DFS Paths)을 모두 수행합니다.
"""
import argparse
from uuid import UUID

import sys
import os

# 프로젝트 루트 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from services.analysis_service import AnalysisService

def run_full_analysis(run_id: UUID):
    """전체 분석 실행 함수 (하위 호환용)"""
    return AnalysisService.run_full_analysis(run_id)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perform full analysis for a Run.")
    parser.add_argument("run_id", help="Run UUID to analyze")
    args = parser.parse_args()
    
    try:
        rid = UUID(args.run_id)
        run_full_analysis(rid)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

