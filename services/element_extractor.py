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

    def extract(self) -> list:
        """
        Parses DOM and CSS to find interactive elements and return them as a list of dictionaries.
        """
        results = []
        try:
            with sync_playwright() as p:
                # Launch browser
                # headless=True is default.
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                # Prepare HTML with CSS injected
                # Basic strategy: Wrap in html/body if missing, inject style in head
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
                # waitUntil 'domcontentloaded' or 'networkidle' is not applicable for set_content easily without goto,
                # but set_content waits for load.
                page.set_content(full_html)

                self.logger.info("Evaluating page to find elements...")
                results = page.evaluate("""() => {
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
                        return 'rgba(0, 0, 0, 0)'; // Fallback
                    };

                    // Selectors for Semantic Elements
                    const selectors = [
                        'button', 
                        'a', 
                        'input', 
                        'textarea', 
                        'select'
                    ];

                    // 1. Semantic Elements
                    selectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            if (!processedElements.has(el)) {
                                processedElements.add(el);
                                
                                let type = el.tagName.toLowerCase();
                                if (type === 'a') type = 'link';

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
                                    tabindex: el.getAttribute('tabindex'),
                                    disabled: el.disabled || el.getAttribute('aria-disabled') === 'true',
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

                    return foundElements;
                }""")
                
                browser.close()
        except Exception as e:
            self.logger.error(f"Error extracting elements: {e}")
            raise e
            
        return results
