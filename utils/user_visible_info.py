"""일반 사용자가 인지할 수 있는 페이지 정보 수집 유틸리티"""
from typing import Dict, List, Any
from playwright.async_api import Page


async def collect_user_visible_info(page: Page) -> Dict[str, Any]:
    """
    일반 웹사이트 사용자가 인지할 수 있는 정보만 수집합니다.
    
    Args:
        page: Playwright Page 객체
    
    Returns:
        사용자가 인지할 수 있는 정보 딕셔너리
    """
    info = {
        "page_title": "",
        "headings": [],  # 제목들 (h1, h2, h3 등)
        "paragraphs": [],  # 문단 텍스트
        "buttons": [],  # 버튼 텍스트
        "links": [],  # 링크 텍스트와 href
        "input_labels": [],  # 입력 필드 라벨/플레이스홀더
        "visible_text": ""  # 페이지의 주요 텍스트 콘텐츠
    }
    
    try:
        # 페이지 제목
        info["page_title"] = await page.title()
    except:
        pass
    
    try:
        # 제목들 수집 (h1, h2, h3)
        for tag in ["h1", "h2", "h3"]:
            elements = await page.query_selector_all(tag)
            for element in elements[:5]:  # 각 타입당 최대 5개
                try:
                    if await element.is_visible():
                        text = (await element.inner_text()).strip()
                        if text:
                            info["headings"].append(f"{tag}: {text[:100]}")
                except:
                    continue
    except:
        pass
    
    try:
        # 주요 문단 텍스트 수집
        paragraphs = await page.query_selector_all("p")
        for p in paragraphs[:10]:  # 최대 10개
            try:
                if await p.is_visible():
                    text = (await p.inner_text()).strip()
                    if text and len(text) > 10:  # 최소 10자 이상
                        info["paragraphs"].append(text[:200])  # 최대 200자
            except:
                continue
    except:
        pass
    
    try:
        # 버튼 텍스트 수집
        buttons = await page.query_selector_all("button, input[type='button'], input[type='submit']")
        for btn in buttons[:20]:  # 최대 20개
            try:
                if await btn.is_visible():
                    text = (await btn.inner_text()).strip()
                    if not text:
                        # inner_text가 없으면 value 속성 확인
                        text = await btn.get_attribute("value") or ""
                    if text:
                        info["buttons"].append(text[:50])
            except:
                continue
    except:
        pass
    
    try:
        # 링크 텍스트와 href 수집
        links = await page.query_selector_all("a[href]")
        for link in links[:20]:  # 최대 20개
            try:
                if await link.is_visible():
                    text = (await link.inner_text()).strip()
                    href = await link.get_attribute("href") or ""
                    if text:
                        info["links"].append(f"{text[:50]}: {href[:100]}")
            except:
                continue
    except:
        pass
    
    try:
        # 입력 필드 라벨/플레이스홀더 수집
        inputs = await page.query_selector_all("input, textarea, select")
        for inp in inputs[:15]:  # 최대 15개
            try:
                if await inp.is_visible():
                    # 라벨 찾기
                    label_text = ""
                    input_id = await inp.get_attribute("id")
                    if input_id:
                        label = await page.query_selector(f"label[for='{input_id}']")
                        if label:
                            label_text = (await label.inner_text()).strip()
                    
                    # 플레이스홀더
                    placeholder = await inp.get_attribute("placeholder") or ""
                    
                    # aria-label
                    aria_label = await inp.get_attribute("aria-label") or ""
                    
                    # 가장 적절한 라벨 선택
                    final_label = label_text or placeholder or aria_label
                    if final_label:
                        info["input_labels"].append(final_label[:50])
            except:
                continue
    except:
        pass
    
    try:
        # 페이지의 주요 텍스트 콘텐츠 (body에서 직접 추출, 최대 500자)
        body_text = await page.evaluate("""
            () => {
                const body = document.body;
                if (!body) return '';
                const text = body.innerText || body.textContent || '';
                return text.trim().substring(0, 500);
            }
        """)
        info["visible_text"] = body_text
    except:
        pass
    
    return info
