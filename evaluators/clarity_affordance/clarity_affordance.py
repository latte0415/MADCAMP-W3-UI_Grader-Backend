import json
import os
import re

def parse_color(color_str):
    """rgb(r, g, b) 또는 rgba(r, g, b, a) 문자열을 숫자리스트로 변환"""
    if not color_str: return [0, 0, 0]
    nums = re.findall(r"(\d+(?:\.\d+)?)", color_str)
    return [float(n) for n in nums[:3]] # R, G, B만 사용

def get_luminance(rgb):
    """WCAG 2.1 relative luminance 계산"""
    colors = []
    for c in rgb:
        c /= 255.0
        if c <= 0.03928:
            colors.append(c / 12.92)
        else:
            colors.append(((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * colors[0] + 0.7152 * colors[1] + 0.0722 * colors[2]

def get_contrast_ratio(rgb1, rgb2):
    """두 색상 간의 대비비 계산"""
    l1 = get_luminance(rgb1)
    l2 = get_luminance(rgb2)
    brightest = max(l1, l2)
    darkest = min(l1, l2)
    return (brightest + 0.05) / (darkest + 0.05)

def check_accessibility(json_path=None, data=None):
    if data is None:
        if not json_path or not os.path.exists(json_path):
            print(f"Error: {json_path} not found.")
            return None

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

    elements = data.get('elements', [])
    url = data.get('url', 'Unknown URL')
    
    print(f"--- Accessibility & Usability Checklist Result for {url} ---")
    print(f"Total elements analyzed: {len(elements)}\n")

    json_results = {
        "url": url,
        "summary": {
            "total_elements": len(elements),
            "passed_count": 0,
            "failed_count": 0
        },
        "details": {
            "semantic_and_attribute": {"pass": [], "fail": []},
            "visual_rules": {"pass": [], "fail": []}
        }
    }

    for el in elements:
        tag = el.get('tag', 'unknown')
        el_type = el.get('type')
        role = el.get('role')
        tabindex = el.get('tabindex')
        aria_label = (el.get('aria_label') or "").lower()
        title = (el.get('title') or "").lower()
        text = el.get('text', '').strip() or el.get('placeholder', '') or 'No Text'
        styles = el.get('styles', {})
        disabled_styles = el.get('disabled_styles')
        rect = el.get('rect', {})
        
        el_info = {
            "tag": tag,
            "text": text,
            "id": el.get('id'),
            "class": el.get('class'),
            "type": el_type
        }

        issues_semantic = []
        issues_visual = []

        # --- 1. 시맨틱 및 속성 규칙 ---
        
        # [표준 태그 사용 및 role/tabindex]
        if el_type in ["button", "button_custom", "link"]:
            # 표준 태그 사용 여부
            if el_type == "button" and tag not in ["button", "input"]:
                issues_semantic.append(f"Non-standard tag <{tag}> used for button")
            elif el_type == "link" and tag != "a":
                issues_semantic.append(f"Non-standard tag <{tag}> used for link")
            
            # 비시맨틱 요소의 role/tabindex (div, span)
            if tag in ["div", "span"]:
                if role != "button":
                    issues_semantic.append(f"Custom button <{tag}> missing role='button'")
                if not tabindex or tabindex == "-1":
                    issues_semantic.append(f"Custom button <{tag}> missing/invalid tabindex")

        # [텍스트 존재 여부]
        if el_type in ["button", "button_custom"]:
            actual_text = el.get('text', '').strip()
            if not actual_text and not aria_label and not title:
                issues_semantic.append("Button has no text and no accessibility label (aria-label/title)")

        # [상태 표시기 - Disabled]
        is_disabled = el.get('disabled', False)
        if disabled_styles and el_type != "input":
            diff_found = False
            for prop in ["backgroundColor", "opacity", "color", "border"]:
                if styles.get(prop) != disabled_styles.get(prop):
                    diff_found = True
                    break
            
            if is_disabled:
                # 이미 비활성화된 경우, 커서나 투명도 등으로 구분이 되는지 확인
                if styles.get('cursor') != 'not-allowed' and float(styles.get('opacity', '1') or '1') >= 1:
                    issues_semantic.append("Disabled element lacks clear visual distinction (cursor/opacity)")
            elif not diff_found:
                issues_semantic.append("No visual change detected for disabled state")

        # --- 2. 시각적 규칙 ---

        if el_type in ["button", "button_custom", "link"]:
            # Cursor Check
            cursor = styles.get("cursor")
            if is_disabled:
                if cursor == "pointer":
                    issues_visual.append("Disabled element should not have 'pointer' cursor")
            else:
                if cursor == "not-allowed":
                    issues_visual.append("Enabled element has 'not-allowed' cursor")
                elif cursor != "pointer":
                    issues_visual.append(f"Cursor is '{cursor}' instead of 'pointer'")
            
            # Size Check (44x44 rule)
            width = rect.get('width', 0) if rect else 0
            height = rect.get('height', 0) if rect else 0
            
            # size fallback logic...
            if width <= 0 or height <= 0:
                try:
                    # 'px' 등을 제거하고 숫자로 변환
                    style_w = styles.get("width", "0").replace("px", "").strip()
                    style_h = styles.get("height", "0").replace("px", "").strip()
                    width = float(style_w) if style_w else 0
                    height = float(style_h) if style_h else 0
                except:
                    pass

            if width < 44 or height < 44:
                issues_visual.append(f"Interactive area too small: {int(width)}x{int(height)}px (Min 44x44px)")
            
            # [Color Contrast Checks]
            btn_bg = parse_color(styles.get("backgroundColor"))
            btn_text = parse_color(styles.get("color"))
            parent_bg = parse_color(el.get("parent_backgroundColor"))

            # 비교 1: 버튼 배경색 vs 글자색 (WCAG AA standard: 4.5:1)
            contrast_text = get_contrast_ratio(btn_bg, btn_text)
            if contrast_text < 4.5:
                issues_visual.append(f"Low text contrast: {contrast_text:.2f}:1 (Min 4.5:1 recommended)")

            # 비교 2: 버튼 배경색 vs 컨테이너 배경색 (Min 3.0:1 for visibility)
            # 단, 배경이 투명하지 않은 경우에만 의미가 있음
            if styles.get("backgroundColor") != "rgba(0, 0, 0, 0)" and "transparent" not in styles.get("backgroundColor", ""):
                contrast_container = get_contrast_ratio(btn_bg, parent_bg)
                if contrast_container < 3.0:
                    issues_visual.append(f"Low button visibility against background: {contrast_container:.2f}:1 (Min 3.0:1 recommended)")

            # Border Check
            has_border = styles.get("borderStyle") != "none" and styles.get("borderWidth") != "0px"
            if not has_border and (styles.get("backgroundColor") == "rgba(0, 0, 0, 0)" or "transparent" in styles.get("backgroundColor", "")):
                issues_visual.append("Transparent button/link missing border for visual contrast")

        # 결과 분류 및 기록
        if issues_semantic:
            json_results["details"]["semantic_and_attribute"]["fail"].append({**el_info, "issues": issues_semantic})
        else:
            json_results["details"]["semantic_and_attribute"]["pass"].append(el_info)
            
        if issues_visual:
            json_results["details"]["visual_rules"]["fail"].append({**el_info, "issues": issues_visual})
        else:
            json_results["details"]["visual_rules"]["pass"].append(el_info)

        # Summary Count (하나라도 실패하면 실패로 간주)
        if not issues_semantic and not issues_visual:
            json_results["summary"]["passed_count"] += 1
        else:
            json_results["summary"]["failed_count"] += 1

    # 터미널 출력
    sections = [
        ("1. 시맨틱 및 속성 규칙", "semantic_and_attribute"),
        ("2. 시각적 규칙", "visual_rules")
    ]

    for title, key in sections:
        print(f"### {title}")
        fail_list = json_results["details"][key]["fail"]
        if not fail_list:
            print("  - [PASS] No issues found.")
        else:
            # 요소별로 이슈 나열
            for item in fail_list:
                issues_str = ", ".join(item["issues"])
                print(f"  - [FAIL] {item['tag']} ('{item['text']}'): {issues_str}")
        print()

    # JSON 파일 저장 (path가 있을 때만)
    if json_path:
        output_path = os.path.join(os.path.dirname(json_path), "checklist_results.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(json_results, f, indent=2, ensure_ascii=False)
        print(f"--- Results saved to {output_path} ---")

    print(f"Summary: Total {len(elements)}, Passed {json_results['summary']['passed_count']}, Failed {json_results['summary']['failed_count']}")
    
    return json_results

if __name__ == "__main__":
    json_file_path = os.path.join(os.path.dirname(__file__), "..", "elements.json")
    check_accessibility(json_file_path)
