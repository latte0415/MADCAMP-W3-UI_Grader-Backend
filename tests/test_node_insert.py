"""노드 삽입 테스트 스크립트"""
import os
import sys
import asyncio
from pathlib import Path
from uuid import uuid4, UUID
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from infra.supabase import get_client
from services.node_service import create_or_get_node, get_node_with_artifacts


def create_test_run(target_url: str, start_url: str) -> str:
    """
    테스트용 run 생성
    
    Args:
        target_url: 탐색 대상 웹사이트 URL
        start_url: 시작 URL
    
    Returns:
        run_id (UUID 문자열)
    """
    supabase = get_client()
    
    run_data = {
        "target_url": target_url,
        "start_url": start_url,
        "status": "running",
        "metadata": {"test": True}
    }
    
    result = supabase.table("runs").insert(run_data).execute()
    
    if result.data and len(result.data) > 0:
        return result.data[0]["id"]
    else:
        raise Exception("Run 생성 실패")


async def test_node_insert():
    """노드 삽입 테스트"""
    # 테스트 URL
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/login")
    
    print("=" * 50)
    print("노드 삽입 테스트 시작")
    print("=" * 50)
    
    try:
        # 1. Run 생성
        print(f"\n1. Run 생성 중...")
        print(f"   Target URL: {target_url}")
        print(f"   Start URL: {start_url}")
        run_id = create_test_run(target_url, start_url)
        print(f"   ✓ Run ID: {run_id}")
        
        # 2. Playwright로 페이지 열기
        print(f"\n2. 페이지 로드 중...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            
            print(f"   페이지 이동: {start_url}")
            await page.goto(start_url, wait_until="networkidle")
            print(f"   ✓ 페이지 로드 완료")
            
            # 3. 노드 생성
            print(f"\n3. 노드 생성 중...")
            node = await create_or_get_node(UUID(run_id), page)
            print(f"   ✓ 노드 생성 완료")
            print(f"   Node ID: {node['id']}")
            print(f"   URL: {node['url']}")
            print(f"   URL Normalized: {node['url_normalized']}")
            print(f"   A11y Hash: {node['a11y_hash'][:16]}...")
            print(f"   State Hash: {node['state_hash'][:16]}...")
            print(f"   Auth State: {node['auth_state']}")
            print(f"   DOM Snapshot Ref: {node.get('dom_snapshot_ref')}")
            print(f"   CSS Snapshot Ref: {node.get('css_snapshot_ref')}")
            
            # 4. 아티팩트 확인
            print(f"\n4. 아티팩트 조회 중...")
            node_with_artifacts = get_node_with_artifacts(UUID(node["id"]))
            css_snapshot = None
            if node_with_artifacts and node_with_artifacts.get("artifacts"):
                css_snapshot = node_with_artifacts["artifacts"].get("css_snapshot")
            if css_snapshot:
                print(f"   ✓ CSS 스냅샷 로드됨 (length={len(css_snapshot)})")
            else:
                print(f"   ✗ CSS 스냅샷 로드 실패 또는 비어있음")

            # 5. 중복 테스트 (같은 페이지에서 다시 노드 생성)
            print(f"\n5. 중복 노드 테스트 (같은 페이지에서 다시 생성)...")
            node2 = await create_or_get_node(UUID(run_id), page)
            if node['id'] == node2['id']:
                print(f"   ✓ 중복 노드가 올바르게 처리됨 (같은 ID 반환)")
            else:
                print(f"   ✗ 중복 노드 처리 실패 (다른 ID 반환)")
            
            await browser.close()
        
        print(f"\n✓ 테스트 완료")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_node_insert())
