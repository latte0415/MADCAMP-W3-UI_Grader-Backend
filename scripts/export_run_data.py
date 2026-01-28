#!/usr/bin/env python3
"""run_id를 입력받아 해당 run의 node, edge 정보를 JSON 파일로 추출하는 스크립트"""
import sys
import json
from uuid import UUID
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from repositories.node_repository import get_nodes_by_run_id
from repositories.edge_repository import get_edges_by_run_id
from utils.logger import get_logger

logger = get_logger(__name__)


def export_run_data(run_id: UUID, output_dir: Path = None) -> str:
    """
    run_id에 해당하는 node, edge 데이터를 JSON 파일로 추출
    
    Args:
        run_id: 추출할 run ID
        output_dir: 출력 디렉토리 (기본값: 프로젝트 루트)
    
    Returns:
        생성된 파일 경로
    """
    if output_dir is None:
        output_dir = Path(__file__).parent.parent
    
    # 노드 데이터 조회
    logger.info(f"노드 데이터 조회 중: {run_id}")
    nodes = get_nodes_by_run_id(run_id)
    logger.info(f"노드 {len(nodes)}개 조회 완료")
    
    # 엣지 데이터 조회
    logger.info(f"엣지 데이터 조회 중: {run_id}")
    edges = get_edges_by_run_id(run_id)
    logger.info(f"엣지 {len(edges)}개 조회 완료")
    
    # 데이터 구조화
    export_data = {
        "run_id": str(run_id),
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "success_edge_count": sum(1 for e in edges if e.get("outcome") == "success"),
            "fail_edge_count": sum(1 for e in edges if e.get("outcome") == "fail"),
        },
        "nodes": nodes,
        "edges": edges,
    }
    
    # 파일명 생성
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"run_data_{str(run_id)}_{timestamp}.json"
    # raw_data/run_data 디렉터리 사용
    run_data_dir = output_dir / "raw_data" / "run_data"
    run_data_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_data_dir / filename
    
    # JSON 파일로 저장
    logger.info(f"데이터 저장 중: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
    
    logger.info(f"✅ 데이터 추출 완료: {output_path}")
    logger.info(f"   - 노드: {len(nodes)}개")
    logger.info(f"   - 엣지: {len(edges)}개 (성공: {export_data['summary']['success_edge_count']}개, 실패: {export_data['summary']['fail_edge_count']}개)")
    
    return str(output_path)


def main():
    """메인 함수"""
    if len(sys.argv) < 2:
        print("사용법: python export_run_data.py <run_id> [output_dir]")
        print("예시: python export_run_data.py 38e1e849-0e66-4635-a13b-fda339e95b07")
        print("예시: python export_run_data.py 38e1e849-0e66-4635-a13b-fda339e95b07 ./exports")
        sys.exit(1)
    
    run_id_str = sys.argv[1]
    
    try:
        run_id = UUID(run_id_str)
    except ValueError:
        print(f"❌ 잘못된 UUID 형식: {run_id_str}")
        sys.exit(1)
    
    # 출력 디렉토리 설정
    output_dir = None
    if len(sys.argv) >= 3:
        output_dir = Path(sys.argv[2])
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # 데이터 추출
    try:
        output_path = export_run_data(run_id, output_dir)
        print(f"\n✅ 추출 완료: {output_path}")
    except Exception as e:
        logger.error(f"데이터 추출 중 오류 발생: {e}", exc_info=True)
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
