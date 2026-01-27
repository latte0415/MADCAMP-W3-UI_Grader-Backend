import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        url = "http://localhost:5173/phase1_analyze"
        print(f"Navigating to {url} ...")
        
        try:
            await page.goto(url)
            # networkidle might be too strict if there's polling, but good for initial load
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except:
                print("Timeout waiting for networkidle, proceeding...")

            print(f"Initial URL: {page.url}")
            
            # Find buttons
            buttons = page.locator("button")
            count = await buttons.count()
            print(f"Found {count} buttons.")

            target_button = None
            
            for i in range(count):
                btn = buttons.nth(i)
                text = await btn.inner_text()
                print(f"Button {i+1}: {text}")
                
                # Heuristic to pick the likely button if multiple
                if "ambiguous" in text.lower() or "go to" in text.lower():
                    target_button = btn
            
            if count == 0:
                print("No buttons found on the page.")
            else:
                # If no specific target found but buttons exist, click the first one
                if not target_button:
                    print("No specific target button identified ('ambiguous' or 'go to'), clicking the first button.")
                    target_button = buttons.first
                
                print(f"Clicking button: '{await target_button.inner_text()}'")
                await target_button.click()
                
                # Wait a bit for navigation
                await page.wait_for_timeout(2000)
                
                print(f"Final URL: {page.url}")
                
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
