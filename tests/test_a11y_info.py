"""a11y_info 추출 테스트 스크립트"""
import sys
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from utils.state_collector import collect_a11y_info


async def test_collect_a11y_info() -> None:
    """
    접근성 정보가 정상적으로 추출되는지 확인합니다.
    - role
    - aria-label
    - aria-labelledby
    - 텍스트 콘텐츠(버튼/링크)
    """
    html = """
    <html>
      <body>
        <button aria-label="닫기">X</button>
        <a href="/signup">회원가입</a>
        <div id="dlg_title">로그인 오류</div>
        <div role="dialog" aria-labelledby="dlg_title"></div>
        <input type="text" aria-label="이메일" />
      </body>
    </html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html)

        a11y_info = await collect_a11y_info(page)
        print("a11y_info:", a11y_info)

        expected = {
            "button|닫기|X|button||",
            "link||회원가입|a||",
            "dialog||로그인 오류|div||",
            "textbox|이메일||input|text|",
        }

        if not expected.issubset(set(a11y_info)):
            missing = expected.difference(set(a11y_info))
            raise AssertionError(f"누락된 항목: {sorted(missing)}")

        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(test_collect_a11y_info())
        print("✓ a11y_info 추출 테스트 통과")
    except Exception as e:
        print(f"✗ a11y_info 추출 테스트 실패: {e}")
        sys.exit(1)
