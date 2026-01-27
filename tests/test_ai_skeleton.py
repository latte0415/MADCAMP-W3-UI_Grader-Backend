import sys
import os
import asyncio
import base64
from pathlib import Path
from playwright.async_api import async_playwright
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from infra.supabase import get_client
from services.ai_service import AiService
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


async def test_ai_skeleton() -> None:
    ai_service = AiService()
    response = await ai_service.get_ai_response()
    print(response)

async def test_ai_skeleton_with_calculator_tools() -> None:
    ai_service = AiService()
    response = await ai_service.get_ai_response_with_calculator_tools()
    print(response)

async def _create_node_with_playwright(run_id: str, start_url: str) -> dict:
    """Playwright로 노드 생성"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        
        await page.goto(start_url, wait_until="networkidle")
        
        # 노드 생성
        from uuid import UUID
        node = await create_or_get_node(UUID(run_id), page)
        
        await browser.close()
        return node


async def test_ai_photo_test() -> None:
    """Playwright로 노드 생성 후 스크린샷으로 photo-test 실행"""
    # 테스트 URL
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/login")
    
    print("=" * 50)
    print("AI Photo Test 테스트 시작")
    print("=" * 50)
    
    try:
        # 1. Run 생성
        print(f"\n1. Run 생성 중...")
        print(f"   Target URL: {target_url}")
        print(f"   Start URL: {start_url}")
        run_id = create_test_run(target_url, start_url)
        print(f"   ✓ Run ID: {run_id}")
        
        # 2. Playwright로 페이지 열기 및 노드 생성
        print(f"\n2. 페이지 로드 및 노드 생성 중...")
        node = await _create_node_with_playwright(run_id, start_url)
        print(f"   ✓ 페이지 로드 완료")
        print(f"   ✓ 노드 생성 완료: {node['id']}")
        node_url = node['url']
        
        # 3. 노드 아티팩트에서 스크린샷 가져오기
        print(f"\n3. 노드 아티팩트 조회 중...")
        from uuid import UUID
        node_with_artifacts = get_node_with_artifacts(UUID(node['id']))
        
        if node_with_artifacts and node_with_artifacts.get("artifacts"):
            screenshot_bytes = node_with_artifacts["artifacts"].get("screenshot_bytes")
        
        if not screenshot_bytes:
            raise Exception("스크린샷을 찾을 수 없습니다. 노드 아티팩트에 screenshot_bytes가 없습니다.")
        
        print(f"   ✓ 스크린샷 로드됨 (size={len(screenshot_bytes)} bytes)")
        
        # 4. 스크린샷을 base64로 인코딩
        print(f"\n4. 스크린샷을 base64로 인코딩 중...")
        image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        print(f"   ✓ Base64 인코딩 완료 (length={len(image_base64)})")
        
        # 5. 보조 자료 준비 (사용자가 인지할 수 있는 정보만)
        auxiliary_data = {
            "url": node_url,
            "viewport": "1280x720"
        }
        
        # 6. AI photo-test 실행
        print(f"\n5. AI photo-test 실행 중...")
        ai_service = AiService()
        response = await ai_service.get_ai_response_with_photo(
            image_base64=image_base64,
            auxiliary_data=auxiliary_data
        )
        
        print(f"\n✓ AI 응답:")
        print("-" * 50)
        print(response)
        print("-" * 50)
        
        print(f"\n✓ 테스트 완료")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def test_update_run_memory() -> None:
    """Playwright로 노드 생성 후 페이지 정보로 update-run-memory 실행"""
    # 테스트 URL
    target_url = os.getenv("TEST_TARGET_URL", "https://madcamp-w2-decision-maker-web.vercel.app")
    start_url = os.getenv("TEST_START_URL", "https://madcamp-w2-decision-maker-web.vercel.app/login")
    
    print("=" * 50)
    print("Update Run Memory 테스트 시작")
    print("=" * 50)
    
    try:
        # 1. Run 생성
        print(f"\n1. Run 생성 중...")
        print(f"   Target URL: {target_url}")
        print(f"   Start URL: {start_url}")
        run_id_str = create_test_run(target_url, start_url)
        print(f"   ✓ Run ID: {run_id_str}")
        
        from uuid import UUID
        run_id = UUID(run_id_str)
        
        # 2. Playwright로 페이지 열기 및 노드 생성
        print(f"\n2. 페이지 로드 및 노드 생성 중...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            await page.goto(start_url, wait_until="networkidle")
            
            node = await create_or_get_node(run_id, page)
            node_url = node['url']
            print(f"   ✓ 페이지 로드 완료")
            print(f"   ✓ 노드 생성 완료: {node['id']}")
            
            # 3. 일반 사용자가 인지할 수 있는 페이지 정보 수집
            print(f"\n3. 페이지 정보 수집 중...")
            from utils.user_visible_info import collect_user_visible_info
            page_state = await collect_user_visible_info(page)
            print(f"   ✓ 페이지 정보 수집 완료: 제목={len(page_state.get('headings', []))}, 버튼={len(page_state.get('buttons', []))}, 링크={len(page_state.get('links', []))}")
            
            # # 이미지 사용 시 (주석 처리)
            # print(f"\n3. 노드 아티팩트 조회 중...")
            # node_with_artifacts = get_node_with_artifacts(UUID(node['id']))
            # 
            # if node_with_artifacts and node_with_artifacts.get("artifacts"):
            #     screenshot_bytes = node_with_artifacts["artifacts"].get("screenshot_bytes")
            # 
            # if not screenshot_bytes:
            #     raise Exception("스크린샷을 찾을 수 없습니다. 노드 아티팩트에 screenshot_bytes가 없습니다.")
            # 
            # print(f"   ✓ 스크린샷 로드됨 (size={len(screenshot_bytes)} bytes)")
            # 
            # # 4. 스크린샷을 base64로 인코딩
            # print(f"\n4. 스크린샷을 base64로 인코딩 중...")
            # image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            # print(f"   ✓ Base64 인코딩 완료 (length={len(image_base64)})")
            
            # 4. 보조 자료 준비 (사용자가 인지할 수 있는 정보만)
            auxiliary_data = {
                "url": node_url,
                "viewport": "1280x720"
            }
            
            # 5. AI update-run-memory 실행
            print(f"\n4. AI update-run-memory 실행 중...")
            print(f"   Run ID: {run_id}")
            ai_service = AiService()
            updated_memory, has_changes = await ai_service.update_run_memory_with_ai(
                run_id=run_id,
                auxiliary_data=auxiliary_data,
                page_state=page_state  # 사용자 인지 가능한 정보 전달
                # image_base64 파라미터는 더 이상 사용하지 않음 (제거됨)
            )
            
            await browser.close()
        
            print(f"\n✓ AI 응답:")
            print("-" * 50)
            print(f"   수정사항 여부: {has_changes}")
            print(f"   업데이트된 메모리: {updated_memory}")
            print("-" * 50)
            
            # 6. run_memory 확인
            print(f"\n5. run_memory 확인 중...")
            from repositories.ai_memory_repository import get_run_memory
            run_memory = get_run_memory(run_id)
            if run_memory:
                print(f"   ✓ Run Memory 조회 성공")
                content = run_memory.get('content', {})
                print(f"   Content 키: {list(content.keys())}")
                print(f"   Content 내용: {content}")
            else:
                print(f"   ⚠ Run Memory가 아직 생성되지 않았습니다.")
            
            print(f"\n✓ 테스트 완료")
            print("=" * 50)
        
    except Exception as e:
        print(f"\n✗ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__": 

    print("=" * 50)
    print("AI Skeleton Test 시작")
    print("=" * 50)
    try:
        asyncio.run(test_ai_skeleton())
        print("✓ ai_skeleton 테스트 통과")
    except Exception as e:
        print(f"✗ ai_skeleton 테스트 실패: {e}")
        sys.exit(1)
    
    # print("=" * 50)
    # print("AI Calculator Tools Test 시작")
    # print("=" * 50)
    # try:
    #     asyncio.run(test_ai_skeleton_with_calculator_tools())
    #     print("✓ ai_skeleton_with_calculator_tools 테스트 통과")
    # except Exception as e:
    #     print(f"✗ ai_skeleton_with_calculator_tools 테스트 실패: {e}")
    #     sys.exit(1)
    
    # print("=" * 50)
    # print("AI Photo Test 테스트 시작")
    # print("=" * 50)
    # try:
    #     asyncio.run(test_ai_photo_test())
    #     print("✓ ai_photo_test 테스트 통과")
    # except Exception as e:
    #     print(f"✗ ai_photo_test 테스트 실패: {e}")
    #     sys.exit(1)
    
    print("=" * 50)
    print("Update Run Memory 테스트 시작")
    print("=" * 50)
    try:
        asyncio.run(test_update_run_memory())
        print("✓ update_run_memory 테스트 통과")
    except Exception as e:
        print(f"✗ update_run_memory 테스트 실패: {e}")
        sys.exit(1)