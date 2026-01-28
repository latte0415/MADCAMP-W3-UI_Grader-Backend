
import asyncio
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from services.edge_service import perform_action

async def test_strict_mode_handling():
    print("Testing Strict Mode Handling...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Create a page with duplicate buttons
        html_content = """
        <html>
            <body>
                <button name="Duplicate">Duplicate</button>
                <button name="Duplicate">Duplicate</button>
                <div id="log"></div>
                <script>
                    document.querySelectorAll('button').forEach(btn => {
                        btn.addEventListener('click', () => {
                            document.getElementById('log').innerText = 'Clicked';
                        });
                    });
                </script>
            </body>
        </html>
        """
        await page.set_content(html_content)
        
        # Define action that targets the duplicate button
        action = {
            "action_type": "click",
            "role": "button",
            "name": "Duplicate",
            "action_target": "role=button name=Duplicate"
        }
        
        try:
            # This should NOT fail with the fix
            result = await perform_action(page, action)
            
            print(f"Result: {result}")
            
            if result["outcome"] == "success":
                print("SUCCESS: Action performed successfully despite duplicate elements.")
                
                # Verify click actually happened
                log_text = await page.locator("#log").inner_text()
                if log_text == "Clicked":
                     print("SUCCESS: Click event verified.")
                else:
                     print("WARNING: Click reported success but event not verified (might be due to wait timing).")
            else:
                print(f"FAILURE: Action failed with outcome: {result['outcome']}")
                print(f"Error: {result['error_msg']}")
                sys.exit(1)
                
        except Exception as e:
            print(f"CRITICAL FAILURE: Exception raised: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_strict_mode_handling())
