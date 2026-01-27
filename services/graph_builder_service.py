"""그래프 구축 서비스"""
import asyncio
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID
from playwright.async_api import async_playwright

from utils.logger import get_logger, set_context, clear_context

logger = get_logger(__name__)

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from services.node_service import NodeService
from workers.tasks import process_node_worker


async def start_graph_building(run_id: UUID, start_url: str) -> None:
    """
    그래프 구축을 시작합니다.
    
    Args:
        run_id: 탐색 세션 ID
        start_url: 시작 URL
    """
    playwright = None
    browser = None
    
    try:
        set_context(run_id=str(run_id), worker_type="GRAPH_BUILDER")
        logger.info(f"그래프 구축 시작: start_url={start_url}")
        
        # 1. Playwright로 start_url 접속
        logger.info(f"[1/3] 브라우저 시작 및 페이지 로드 중: {start_url}")
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        page = await context.new_page()
        await page.goto(start_url, wait_until="networkidle")
        logger.info(f"[1/3] 페이지 로드 완료")
        
        # 2. 첫 노드 생성
        logger.info(f"[2/3] 첫 노드 생성 중...")
        node_service = NodeService()
        first_node = await node_service.create_or_get_node(run_id, page)
        first_node_id = UUID(first_node["id"])
        first_node_url = first_node.get("url", "unknown")
        logger.info(f"[2/3] 첫 노드 생성 완료: node_id={first_node_id}, url={first_node_url}")
        
        # 3. 첫 워커 생성: process_node_worker에 run_id, node_id 전달
        logger.info(f"[3/3] 첫 워커 생성 중: node_id={first_node_id}")
        message = process_node_worker.send(str(run_id), str(first_node_id))
        message_id = message.message_id if hasattr(message, 'message_id') else 'unknown'
        logger.info(f"[3/3] 워커 메시지 전송 완료: message_id={message_id}")
        logger.info(f"[3/3] ⚠️  워커 프로세스가 실행 중인지 확인하세요: python -m workers.worker")
        logger.info(f"[3/3] 첫 워커 생성 완료 - 그래프 구축 프로세스 시작됨")
        
    except Exception as e:
        logger.error(f"에러 발생: {e}", exc_info=True)
        raise
    finally:
        clear_context()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


def start_graph_building_sync(run_id: UUID, start_url: str) -> None:
    """
    그래프 구축을 시작합니다 (동기 버전).
    
    Args:
        run_id: 탐색 세션 ID
        start_url: 시작 URL
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(start_graph_building(run_id, start_url))
