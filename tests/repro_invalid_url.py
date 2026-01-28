
import asyncio
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from services.edge_service import perform_action

async def test_invalid_url_handling():
    print("Testing Invalid URL Handling...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # We need a web server for strict relative URL testing (protocol requirement), 
        # but playright's set_content usually puts us on "about:blank" or data URL where relative might fail differently.
        # However, page.goto behavior with relative path on a data url might be specific.
        # Let's try to mock it by navigating to a real (but simple) site or using a local file server.
        # Actually, let's just use a data URL and see if we can trick it, or catch the specific "Example" error.
        
        # Scenario: We are on "http://example.com/foo" and try to click a link with href="bar".
        # We want perform_action to try navigating to "http://example.com/bar".
        
        page = await browser.new_page()
        # Navigate to a base URL (doesn't need to be reachable if we just check the call arguments, 
        # but perform_action calls page.goto which will try to connect)
        # Using a reliable public URL for testing navigation logic might be best, or just checking if `page.goto` is called with absolute URL.
        # Since we can't easily spy on page.goto in this script without mocking, let's look at the result.
        
        # Strategy: Use set_content with a <base> tag or just assume we are on a page.
        # But wait, perform_action checks page.url.
        # Let's navigate to a dummy page first.
        try:
             await page.goto("https://example.com")
        except:
             print("Could not navigate to example.com, test might be flaky")
        
        # Create a link with relative path
        html_content = """
        <html>
            <body>
                <a href="relative_page" id="rel_link">Relative Link</a>
            </body>
        </html>
        """
        # We can't really overwrite content of example.com easily without route interception
        # Let's use route interception to mock the base page!
        
        await page.route("http://mock-domain.com/start", lambda route: route.fulfill(body=html_content, content_type="text/html"))
        await page.route("http://mock-domain.com/relative_page", lambda route: route.fulfill(body="<html><body>Success</body></html>", content_type="text/html"))
        
        await page.goto("http://mock-domain.com/start")
        
        action = {
            "action_type": "click",
            "selector": "#rel_link",
            "href": "relative_page"
        }
        
        # Case 1: Click works (normal flow) - mocked route should handle it.
        # Note: edge_service logic only tries manual goto if click doesn't trigger navigation (url change).
        # We want to force the fallback logic?
        # To force fallback, the click must NOT trigger navigation, OR we test the `action_type="navigate"` logic for fallback.
        # In the `click` handler: "if href and page.url == before_url:" -> it tries manual goto.
        # So we need the click to FAIL to navigate essentially, but happen. 
        # Making the link have `onclick="event.preventDefault()"` would simulate a JS link that fails, but here we want to test the `href` fallback for simple links that might have failed for some reason, OR simply test that we handle `href` correctly.
        
        # Let's test the specific case where we use `page.goto` with relative URL which crashes playwright.
        # This happens if we manually execute `page.goto("relative_path")`.
        # So we want to ensure `perform_action` converts it.
        
        # Let's modify the action to simulate a "navigate" action with relative path (which caused part of the issue?)
        # Or checking the `click` fallback. 
        
        # Let's force fallback by preventing default on click
        await page.evaluate("""
            document.getElementById('rel_link').addEventListener('click', (e) => {
                e.preventDefault(); // This stops the browser from navigating automatically
            });
        """)
        
        print("Executing action...")
        result = await perform_action(page, action)
        print(f"Result: {result}")
        
        if result["outcome"] == "success":
             # We expect success because perform_action should detect no URL change, read href, convert to absolute, and goto.
             # And our mock route handles the valid absolute URL.
             if page.url == "http://mock-domain.com/relative_page":
                 print("SUCCESS: Navigated to absolute URL via fallback.")
             else:
                 print(f"FAILURE: Did not navigate to expected URL. Current: {page.url}")
                 sys.exit(1)
        else:
             print(f"FAILURE: Action failed: {result['error_msg']}")
             sys.exit(1)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_invalid_url_handling())
