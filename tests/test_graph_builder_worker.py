"""그래프 구축 워커 테스트 스크립트

비동기 워커를 사용한 그래프 구축 시스템을 테스트합니다.
"""
import os
import sys
import asyncio
import time
from pathlib import Path
from uuid import UUID

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from infra.supabase import get_client
from services.graph_builder_service import start_graph_building
from repositories.ai_memory_repository import get_run_memory, create_run_memory


def get_nodes_by_run_id(run_id: UUID):
    """run_id로 노드 목록 조회"""
    supabase = get_client()
    result = supabase.table("nodes").select("*").eq("run_id", str(run_id)).execute()
    return result.data or []


def get_edges_by_run_id(run_id: UUID):
    """run_id로 엣지 목록 조회"""
    supabase = get_client()
    result = supabase.table("edges").select("*").eq("run_id", str(run_id)).execute()
    return result.data or []


def create_test_run(target_url: str, start_url: str) -> str:
    """테스트용 run 생성"""
    supabase = get_client()
    run_data = {
        "target_url": target_url,
        "start_url": start_url,
        "status": "running",
        "metadata": {"test": True, "test_type": "graph_builder_worker"}
    }
    result = supabase.table("runs").insert(run_data).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]["id"]
    raise Exception("Run 생성 실패")


async def wait_for_workers(max_wait_seconds: int = 60, check_interval: float = 2.0):
    """
    워커가 작업을 처리할 시간을 기다립니다.
    
    Args:
        max_wait_seconds: 최대 대기 시간 (초)
        check_interval: 확인 간격 (초)
    """
    print(f"\n워커 작업 대기 중 (최대 {max_wait_seconds}초)...")
    start_time = time.time()
    
    while time.time() - start_time < max_wait_seconds:
        await asyncio.sleep(check_interval)
        elapsed = int(time.time() - start_time)
        print(f"  대기 중... ({elapsed}초 경과)")
    
    print(f"  대기 완료 ({int(time.time() - start_time)}초 경과)")


async def test_graph_builder_worker_basic():
    """기본 그래프 구축 워커 테스트"""
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/signup")

    print("=" * 50)
    print("그래프 구축 워커 기본 테스트")
    print("=" * 50)

    try:
        # 1. 테스트 run 생성
        print("\n1. Run 생성 중...")
        run_id = create_test_run(target_url, start_url)
        run_id_uuid = UUID(run_id)
        print(f"   ✓ Run ID: {run_id}")

        # 2. 그래프 구축 시작
        print("\n2. 그래프 구축 시작...")
        await start_graph_building(run_id_uuid, start_url)
        print(f"   ✓ 그래프 구축 시작 완료")

        # 3. 워커 작업 대기
        print("\n3. 워커 작업 대기 중...")
        await wait_for_workers(max_wait_seconds=30, check_interval=2.0)

        # 4. 결과 확인
        print("\n4. 결과 확인 중...")
        
        # 노드 확인
        nodes = get_nodes_by_run_id(run_id_uuid)
        print(f"   ✓ 생성된 노드 수: {len(nodes)}")
        if nodes:
            print(f"   - 첫 번째 노드: {nodes[0].get('url')}")
        
        # 엣지 확인
        edges = get_edges_by_run_id(run_id_uuid)
        print(f"   ✓ 생성된 엣지 수: {len(edges)}")
        if edges:
            print(f"   - 첫 번째 엣지: {edges[0].get('action_type')} / {edges[0].get('action_target')}")
        
        # run_memory 확인
        run_memory = get_run_memory(run_id_uuid)
        if run_memory:
            content = run_memory.get("content", {})
            print(f"   ✓ Run Memory 키 수: {len(content)}")
            if content:
                print(f"   - Run Memory 키: {list(content.keys())[:5]}")

        print("\n✓ 기본 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_graph_builder_worker_with_memory():
    """run_memory가 있는 상태에서 그래프 구축 테스트"""
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/signup")

    print("=" * 50)
    print("그래프 구축 워커 (Run Memory 포함) 테스트")
    print("=" * 50)

    try:
        # 1. 테스트 run 생성
        print("\n1. Run 생성 중...")
        run_id = create_test_run(target_url, start_url)
        run_id_uuid = UUID(run_id)
        print(f"   ✓ Run ID: {run_id}")

        # 2. Run Memory 설정
        print("\n2. Run Memory 설정 중...")
        run_memory_content = {
            "ID": "user1@test.com",
            "PW": "Test1234!"
        }
        create_run_memory(run_id_uuid, run_memory_content)
        print(f"   ✓ Run Memory 설정 완료: {run_memory_content}")

        # 3. 그래프 구축 시작
        print("\n3. 그래프 구축 시작...")
        await start_graph_building(run_id_uuid, start_url)
        print(f"   ✓ 그래프 구축 시작 완료")

        # 4. 워커 작업 대기
        print("\n4. 워커 작업 대기 중...")
        await wait_for_workers(max_wait_seconds=60, check_interval=2.0)

        # 5. 결과 확인
        print("\n5. 결과 확인 중...")
        
        # 노드 확인
        nodes = get_nodes_by_run_id(run_id_uuid)
        print(f"   ✓ 생성된 노드 수: {len(nodes)}")
        
        # 엣지 확인
        edges = get_edges_by_run_id(run_id_uuid)
        print(f"   ✓ 생성된 엣지 수: {len(edges)}")
        
        # 입력 액션이 실행되었는지 확인
        fill_edges = [e for e in edges if e.get("action_type") == "fill"]
        print(f"   ✓ Fill 액션 엣지 수: {len(fill_edges)}")
        if fill_edges:
            print(f"   - Fill 액션 예시: {fill_edges[0].get('action_target')} = {fill_edges[0].get('action_value', '')[:30]}...")
        
        # run_memory 업데이트 확인
        updated_memory = get_run_memory(run_id_uuid)
        if updated_memory:
            updated_content = updated_memory.get("content", {})
            print(f"   ✓ 업데이트된 Run Memory 키 수: {len(updated_content)}")
            if updated_content:
                print(f"   - Run Memory 키: {list(updated_content.keys())[:10]}")

        print("\n✓ Run Memory 포함 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_graph_builder_worker_pending_actions():
    """pending actions 처리 테스트"""
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/signup")

    print("=" * 50)
    print("그래프 구축 워커 (Pending Actions) 테스트")
    print("=" * 50)

    try:
        # 1. 테스트 run 생성
        print("\n1. Run 생성 중...")
        run_id = create_test_run(target_url, start_url)
        run_id_uuid = UUID(run_id)
        print(f"   ✓ Run ID: {run_id}")

        # 2. 그래프 구축 시작
        print("\n2. 그래프 구축 시작...")
        await start_graph_building(run_id_uuid, start_url)
        print(f"   ✓ 그래프 구축 시작 완료")

        # 3. 워커 작업 대기 (pending actions 처리를 위해 더 오래 대기)
        print("\n3. 워커 작업 대기 중 (pending actions 처리 포함)...")
        await wait_for_workers(max_wait_seconds=90, check_interval=3.0)

        # 4. 결과 확인
        print("\n4. 결과 확인 중...")
        
        # 노드 확인
        nodes = get_nodes_by_run_id(run_id_uuid)
        print(f"   ✓ 생성된 노드 수: {len(nodes)}")
        
        # 엣지 확인
        edges = get_edges_by_run_id(run_id_uuid)
        print(f"   ✓ 생성된 엣지 수: {len(edges)}")
        
        # pending actions 확인
        from services.pending_action_service import PendingActionService
        pending_service = PendingActionService()
        pending_actions = pending_service.list_pending_actions(
            run_id=run_id_uuid,
            from_node_id=None,
            status="pending"
        )
        print(f"   ✓ 남아있는 Pending Actions 수: {len(pending_actions)}")
        if pending_actions:
            print(f"   - Pending Action 예시: {pending_actions[0].get('action_type')} / {pending_actions[0].get('action_target')}")

        print("\n✓ Pending Actions 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_graph_builder_worker_statistics():
    """그래프 구축 통계 확인 테스트"""
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/signup")

    print("=" * 50)
    print("그래프 구축 워커 통계 테스트")
    print("=" * 50)

    try:
        # 1. 테스트 run 생성
        print("\n1. Run 생성 중...")
        run_id = create_test_run(target_url, start_url)
        run_id_uuid = UUID(run_id)
        print(f"   ✓ Run ID: {run_id}")

        # 2. 그래프 구축 시작
        print("\n2. 그래프 구축 시작...")
        await start_graph_building(run_id_uuid, start_url)
        print(f"   ✓ 그래프 구축 시작 완료")

        # 3. 워커 작업 대기
        print("\n3. 워커 작업 대기 중...")
        await wait_for_workers(max_wait_seconds=60, check_interval=2.0)

        # 4. 통계 수집
        print("\n4. 통계 수집 중...")
        
        nodes = get_nodes_by_run_id(run_id_uuid)
        edges = get_edges_by_run_id(run_id_uuid)
        
        # 노드 통계
        print(f"\n   [노드 통계]")
        print(f"   - 총 노드 수: {len(nodes)}")
        unique_urls = set(node.get("url_normalized") for node in nodes)
        print(f"   - 고유 URL 수: {len(unique_urls)}")
        
        # 엣지 통계
        print(f"\n   [엣지 통계]")
        print(f"   - 총 엣지 수: {len(edges)}")
        action_types = {}
        for edge in edges:
            action_type = edge.get("action_type", "unknown")
            action_types[action_type] = action_types.get(action_type, 0) + 1
        print(f"   - 액션 타입별 분포:")
        for action_type, count in sorted(action_types.items(), key=lambda x: -x[1]):
            print(f"     * {action_type}: {count}개")
        
        # 성공/실패 통계
        success_edges = [e for e in edges if e.get("outcome") == "success"]
        fail_edges = [e for e in edges if e.get("outcome") == "fail"]
        print(f"   - 성공 엣지: {len(success_edges)}개")
        print(f"   - 실패 엣지: {len(fail_edges)}개")
        if len(edges) > 0:
            success_rate = len(success_edges) / len(edges) * 100
            print(f"   - 성공률: {success_rate:.1f}%")
        
        # intent_label 통계
        intent_edges = [e for e in edges if e.get("intent_label")]
        print(f"   - Intent Label이 있는 엣지: {len(intent_edges)}개")

        print("\n✓ 통계 테스트 완료")
        print("=" * 50)

    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="그래프 구축 워커 테스트")
    parser.add_argument(
        "--test",
        choices=["basic", "memory", "pending", "stats", "all"],
        default="basic",
        help="실행할 테스트 (기본값: basic)"
    )
    
    args = parser.parse_args()
    
    if args.test == "basic" or args.test == "all":
        asyncio.run(test_graph_builder_worker_basic())
    
    if args.test == "memory" or args.test == "all":
        asyncio.run(test_graph_builder_worker_with_memory())
    
    if args.test == "pending" or args.test == "all":
        asyncio.run(test_graph_builder_worker_pending_actions())
    
    if args.test == "stats" or args.test == "all":
        asyncio.run(test_graph_builder_worker_statistics())
