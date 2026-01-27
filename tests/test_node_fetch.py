"""노드+아티팩트 조회 테스트 스크립트"""
import sys
import os

# 상위 디렉토리(프로젝트 루트)를 sys.path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from uuid import UUID

from services.node_service import get_node_with_artifacts


def test_node_fetch(node_id: str) -> None:
    """노드+아티팩트 조회 테스트"""
    print("=" * 50)
    print("노드+아티팩트 조회 테스트 시작")
    print("=" * 50)

    try:
        node = get_node_with_artifacts(UUID(node_id))
        if not node:
            raise Exception("해당 node_id를 찾을 수 없습니다.")

        print(f"\n✓ 노드 조회 성공")
        print(f"Node ID: {node['id']}")
        print(f"URL: {node['url']}")

        artifacts = node.get("artifacts", {})
        print("\n아티팩트 로드 결과:")
        print(f"- dom_snapshot_html: {'OK' if artifacts.get('dom_snapshot_html') else 'None'}")
        print(f"- a11y_snapshot: {'OK' if artifacts.get('a11y_snapshot') else 'None'}")
        print(f"- screenshot_bytes: {'OK' if artifacts.get('screenshot_bytes') else 'None'}")
        print(f"- storage_state: {'OK' if artifacts.get('storage_state') else 'None'}")

        print("\n✓ 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_node_fetch.py <node_id>")
        sys.exit(1)

    test_node_fetch(sys.argv[1])
