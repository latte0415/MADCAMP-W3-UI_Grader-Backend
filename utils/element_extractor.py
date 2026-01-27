from playwright.sync_api import sync_playwright
import json
import logging

class ElementExtractor:
    def __init__(self, dom_content: str, css_content: str):
        self.dom_content = dom_content or ""
        self.css_content = css_content or ""
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def extract(self, page=None) -> dict:
        """
        Parses DOM and CSS to find interactive elements.
        Returns a dictionary containing:
        - elements: List of interactive elements with styles
        - status_components: Dictionary of specific components (nav_items, etc.)
        """
        try:
            if page:
                # Use provided page
                return self._process_page(page)
            
            with sync_playwright() as p:
                # Launch browser
                browser = p.chromium.launch(headless=True)
                new_page = browser.new_page()
                result = self._process_page(new_page)
                browser.close()
                return result
        except Exception as e:
            self.logger.error(f"Error extracting elements: {e}")
            raise e

    def _process_page(self, page) -> dict:
        """Internal helper to process a single node on a given page."""
        # Prepare HTML with CSS injected
        full_html = self.dom_content
        
        # Simple heuristic to ensure we have a valid page structure
        if "<html" not in full_html:
            full_html = f"<html><body>{full_html}</body></html>"
        
        if self.css_content:
            style_tag = f"<style>{self.css_content}</style>"
            if "</head>" in full_html:
                full_html = full_html.replace("</head>", f"{style_tag}</head>")
            else:
                # Insert at start of body or just append to html
                 if "<body" in full_html:
                     full_html = full_html.replace("<body", f"<head>{style_tag}</head><body", 1)
                 else:
                     full_html = f"<head>{style_tag}</head>{full_html}"

        self.logger.info("Setting page content...")
        page.set_content(full_html)

        self.logger.info("Evaluating page to find elements...")
        result_data = page.evaluate("""() => {
            const foundElements = [];
            const processedElements = new Set();

            // Helper to get computed styles
            const getStyles = (el) => {
                const s = window.getComputedStyle(el);
                return {
                    color: s.color,
                    backgroundColor: s.backgroundColor,
                    opacity: s.opacity,
                    display: s.display,
                    visibility: s.visibility,
                    cursor: s.cursor,
                    fontSize: s.fontSize,
                    fontWeight: s.fontWeight,
                    textAlign: s.textAlign,
                    borderWidth: s.borderWidth,
                    borderStyle: s.borderStyle,
                    borderColor: s.borderColor,
                    borderRadius: s.borderRadius,
                    width: s.width,
                    height: s.height,
                    position: s.position,
                    zIndex: s.zIndex,
                    textDecoration: s.textDecoration
                };
            };
            
            // Helper to find parent background
            const getParentBg = (el) => {
                let parent = el.parentElement;
                while (parent) {
                    const bg = window.getComputedStyle(parent).backgroundColor;
                    // Check for transparency (rgba(0,0,0,0) or transparent)
                    if (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
                        return bg;
                    }
                    parent = parent.parentElement;
                }
                return 'rgb(255, 255, 255)'; // Fallback to white (standard browser default)
            };

            // Helper to check if element is active (robust check)
            const checkIsActive = (el) => {
                // 1. Aria Check
                const ariaCurrent = el.getAttribute('aria-current');
                if (ariaCurrent && ariaCurrent !== 'false') return true;

                // 2. Class Check
                const className = (el.className || '').toLowerCase();
                if (className.includes('active') || 
                    className.includes('selected') || 
                    className.includes('current')) return true;

                // 3. Style Check (Simple Heuristics)
                const styles = getStyles(el);
                // Font weight bold (700+) or explicit 'bold'
                if (parseInt(styles.fontWeight) >= 700 || styles.fontWeight === 'bold') {
                    return true; 
                }
                if (styles.textDecoration && styles.textDecoration.includes('underline')) return true;
                
                return false;
            };

            // Selectors for Semantic Elements & Structural Headings
            const selectors = [
                'button', 
                'a', 
                'input', 
                'textarea', 
                'select',
                'h1',
                'h2',
                'nav'
            ];

            // 1. Interactive Elements & Headings Extraction
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    if (!processedElements.has(el)) {
                        processedElements.add(el);
                        
                        let type = el.tagName.toLowerCase();
                        if (type === 'a') type = 'link';
                        if (type === 'h1' || type === 'h2') type = 'heading';

                        const rect = el.getBoundingClientRect();
                        const styles = getStyles(el);
                        const parentBg = getParentBg(el);

                        foundElements.push({
                            tag: el.tagName.toLowerCase(),
                            type: type,
                            role: el.getAttribute('role'),
                            id: el.id,
                            class: el.className,
                            text: el.innerText || el.value || '',
                            placeholder: el.getAttribute('placeholder'),
                            title: el.getAttribute('title'),
                            aria_label: el.getAttribute('aria-label'),
                            aria_current: el.getAttribute('aria-current'),
                            aria_selected: el.getAttribute('aria-selected'),
                            aria_pressed: el.getAttribute('aria-pressed'),
                            checked: el.checked,
                            selected: el.selected,
                            tabindex: el.getAttribute('tabindex'),
                            disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
                            rect: {
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height
                            },
                            href: el.getAttribute('href'),
                            styles: styles,
                            parent_backgroundColor: parentBg
                        });
                    }
                });
            });

            // 2. Non-semantic Buttons (role="button")
            document.querySelectorAll('[role="button"]').forEach(el => {
                if (!processedElements.has(el)) {
                    processedElements.add(el);
                    
                    const rect = el.getBoundingClientRect();
                    const styles = getStyles(el);
                    const parentBg = getParentBg(el);

                    foundElements.push({
                        tag: el.tagName.toLowerCase(),
                        type: 'button_custom',
                        role: 'button',
                        id: el.id,
                        class: el.className,
                        text: el.innerText || '',
                        placeholder: null,
                        title: el.getAttribute('title'),
                        aria_label: el.getAttribute('aria-label'),
                        aria_current: el.getAttribute('aria-current'),
                        aria_selected: el.getAttribute('aria-selected'),
                        aria_pressed: el.getAttribute('aria-pressed'),
                        checked: el.getAttribute('aria-checked') === 'true', // role=button usually uses aria-checked if toggle
                        selected: false,
                        tabindex: el.getAttribute('tabindex'),
                        disabled: el.getAttribute('aria-disabled') === 'true',
                        rect: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        styles: styles,
                        parent_backgroundColor: parentBg
                    });
                }
            });


            // 3. Extract Navigation Items (Status Component)
            const navItems = [];
            const navContainers = document.querySelectorAll('nav, [role="navigation"], .nav, .menu, .gnb, .lnb, header');
            navContainers.forEach(container => {
                const links = container.querySelectorAll('a, [role="link"]');
                links.forEach(link => {
                   navItems.push({
                       text: link.innerText || link.getAttribute('aria-label') || '',
                       href: link.getAttribute('href'),
                       is_active: checkIsActive(link)
                   });
                });
            });

            // 4. Extract Breadcrumbs
            const breadcrumbs = [];
            const bcContainers = document.querySelectorAll('nav[aria-label*="Breadcrumb"], .breadcrumb, [itemtype*="BreadcrumbList"]');
            bcContainers.forEach(container => {
                const items = container.querySelectorAll('li, a, span');
                 items.forEach(item => {
                    if (item.innerText.trim()) {
                        breadcrumbs.push({
                            text: item.innerText.trim(),
                            is_active: checkIsActive(item) || item.getAttribute('aria-current') === 'page'
                        });
                    }
                });
            });

            // 5. Extract Progress Indicators
            const progressIndicators = [];
            const progSelectors = [
                '[role="progressbar"]', 
                '[role="status"]', 
                '.spinner', '.loader', '.loading', '.progress', 
                'svg[class*="spinner"]', 'svg[class*="loader"]',
                '[aria-busy="true"]',
                '[id*="spinner"]', '[id*="loader"]', '[id*="loading"]',
                '[class*="spinner"]', '[class*="loader"]', '[class*="loading"]'
            ];
            
            document.querySelectorAll(progSelectors.join(',')).forEach(el => {
                // Filter out invisible ones
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                // Check if it's inside a button or actionable element
                let container = null;
                let parent = el.parentElement;
                while (parent && parent !== document.body) {
                     const tag = parent.tagName.toLowerCase();
                     if (tag === 'button' || tag === 'a' || parent.getAttribute('role') === 'button') {
                         const pRect = parent.getBoundingClientRect();
                         container = {
                             tag: tag,
                             id: parent.id,
                             text: parent.innerText,
                             rect: { x: pRect.x, y: pRect.y, width: pRect.width, height: pRect.height }
                         };
                         break;
                     }
                     parent = parent.parentElement;
                }

                progressIndicators.push({
                    tag: el.tagName.toLowerCase(),
                    class: el.className,
                    role: el.getAttribute('role'),
                    text: el.innerText || '',
                    rect: {
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    },
                    container: container
                });
            });

            return {
                elements: foundElements,
                status_components: {
                    nav_items: navItems,
                    breadcrumbs: breadcrumbs,
                    progress_indicators: progressIndicators
                }
            };
        }""")
        
        return result_data
