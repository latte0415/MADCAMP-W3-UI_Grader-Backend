import json
import os
import re

def check_visibility_of_system_status(json_path=None, data=None):
    if data is None:
        if not json_path or not os.path.exists(json_path):
            print(f"Error: {json_path} not found. Please run the crawler first.")
            return None

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

    url = data.get('url', 'Unknown URL')
    page_title = data.get('title', '')
    status_comps = data.get('status_components', {})
    elements = data.get('elements', [])
    
    print(f"--- Visibility of System Status Checklist Result for {url} ---")

    json_results = {
        "url": url,
        "summary": {
            "title_found": bool(page_title),
            "progress_indicators_found": len(status_comps.get('progress_indicators', [])),
            "breadcrumbs_found": len(status_comps.get('breadcrumbs', [])),
            "active_nav_found": any(item.get('is_active') for item in status_comps.get('nav_items', []))
        },
        "details": {
            "progress_notification": {"pass": [], "fail": [], "info": []},
            "location_and_context": {"pass": [], "fail": [], "info": []},
            "immediate_feedback": {"pass": [], "fail": [], "info": []}
        }
    }

    # --- 1. 진행 상태 알림 (Progress Notifications) ---
    progs = status_comps.get('progress_indicators', [])
    if progs:
        for p in progs:
            json_results["details"]["progress_notification"]["pass"].append({
                "type": p.get('tag') or 'component',
                "description": f"Found progress indicator with class '{p.get('class')}'"
            })
    else:
        # Note: Not necessarily a FAIL if it doesn't need to load, but we can look for 'loading' logic in JS or skeletons
        json_results["details"]["progress_notification"]["info"].append("No explicit progress bars or spinners detected on initial load.")

    # --- 2. 현재 위치 및 맥락 파악 (Location & Context) ---
    
    # [Page Title]
    if page_title and page_title.strip():
        json_results["details"]["location_and_context"]["pass"].append({
            "check": "Page Title",
            "value": page_title
        })
    else:
        json_results["details"]["location_and_context"]["fail"].append({
            "check": "Page Title",
            "issue": "Missing or empty <title> tag"
        })

    # [Breadcrumbs]
    bc = status_comps.get('breadcrumbs', [])
    if bc:
        for b in bc:
            json_results["details"]["location_and_context"]["pass"].append({
                "check": "Breadcrumbs",
                "text": b.get('text')
            })
    else:
        json_results["details"]["location_and_context"]["info"].append("No breadcrumbs pattern detected (Common for single-level apps).")

    # [Active Navigation]
    nav_items = status_comps.get('nav_items', [])
    active_items = [item for item in nav_items if item.get('is_active')]
    if active_items:
        for item in active_items:
            json_results["details"]["location_and_context"]["pass"].append({
                "check": "Active Navigation Highlight",
                "item": item.get('text')
            })
    elif nav_items:
        json_results["details"]["location_and_context"]["fail"].append({
            "check": "Active Navigation Highlight",
            "issue": "Navigation items found but none are visually highlighted as 'active'"
        })
    else:
        json_results["details"]["location_and_context"]["info"].append("No standard navigation elements detected.")

    # --- 3. 행동에 대한 즉각적 피드백 (Immediate Feedback) ---
    
    # [Form Feedback Patterns]
    # Check if any inputs already have error states (e.g. red borders) or validation classes
    form_issues_found = False
    for el in elements:
        if el.get('type') == 'input':
            styles = el.get('styles', {})
            border_color = styles.get('borderColor', '').lower()
            # If it's a "warning/error" color usually red-ish
            if 'rgb(25' in border_color and '0, 0)' in border_color: # Simple red check
                 json_results["details"]["immediate_feedback"]["pass"].append({
                     "check": "Input Error Feedback",
                     "element": el.get('text') or el.get('placeholder'),
                     "issue": "Element currently showing error state (Red border)"
                 })
                 form_issues_found = True

    # [Toast/Alert Presence]
    # Check full doc for role="alert" or "status" or toast classes
    doc = data.get('doc', '')
    toast_patterns = ['role="alert"', 'role="status"', 'class="toast"', 'class="snackbar"', 'aria-live="polite"']
    for pattern in toast_patterns:
        if pattern in doc:
             json_results["details"]["immediate_feedback"]["pass"].append({
                 "check": "Feedback Container",
                 "pattern": pattern,
                 "info": "Infrastructure for immediate feedback (Toast/Alert) detected."
             })

    # Output to terminal
    print("\n### 1. 진행 상태 알림")
    for cat in ["pass", "fail", "info"]:
        for item in json_results["details"]["progress_notification"][cat]:
            prefix = "[PASS]" if cat == "pass" else "[FAIL]" if cat == "fail" else "[INFO]"
            print(f"  - {prefix} {item.get('description') or item}")

    print("\n### 2. 현재 위치 및 맥락 파악")
    for cat in ["pass", "fail", "info"]:
        for item in json_results["details"]["location_and_context"][cat]:
            prefix = "[PASS]" if cat == "pass" else "[FAIL]" if cat == "fail" else "[INFO]"
            desc = item.get('check', '') + ": " + (item.get('value') or item.get('text') or item.get('item') or item.get('issue', ''))
            print(f"  - {prefix} {desc}")

    print("\n### 3. 행동에 대한 즉각적 피드백")
    items_feedback = json_results["details"]["immediate_feedback"]["pass"] + json_results["details"]["immediate_feedback"]["fail"]
    if not items_feedback:
        print("  - [INFO] No immediate feedback components detected on initial page state.")
    else:
        for item in items_feedback:
            print(f"  - [INFO] Found {item.get('check')}: {item.get('info') or item.get('issue') or item.get('element')}")

    # Save to JSON
    if json_path:
        output_dir = os.path.dirname(json_path)
        output_path_final = os.path.join(output_dir, "visibility_results.json")
        with open(output_path_final, "w", encoding="utf-8") as f:
            json.dump(json_results, f, indent=2, ensure_ascii=False)
        
        print(f"\n--- Results saved to {output_path_final} ---")
    
    return json_results

if __name__ == "__main__":
    # elements.json is in the parent directory
    json_file_path = os.path.join(os.path.dirname(__file__), "..", "elements.json")
    check_visibility_of_system_status(json_file_path)
