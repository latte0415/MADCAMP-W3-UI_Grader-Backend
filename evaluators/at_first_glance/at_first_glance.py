import json
import os
import re

def parse_color(color_str):
    """
    CSS 색상 문자열을 파싱하여 [r, g, b] 리스트(0-255)로 반환합니다.
    
    지원하는 형식:
    1. rgb(r, g, b) 또는 rgba(r, g, b, a)
    2. 16진수 코드 (#RRGGBB, #RGB)
    3. 주요 색상명 (white, black, red, green, blue, transparent)
    
    Args:
        color_str (str): 파싱할 CSS 색상 문자열
        
    Returns:
        list: [r, g, b] 형태의 정수/실수 리스트. 파싱 실패 시 [0, 0, 0] 반환.
    """
    if not color_str: return [0, 0, 0]
    color_str = color_str.lower().strip()

    # 1. Named Colors (자주 쓰이는 색상명 처리)
    named_colors = {
        'white': [255, 255, 255],
        'black': [0, 0, 0],
        'transparent': [0, 0, 0], # 배경색 투명은 보통 검정 텍스트와 대비 계산 시 영향 없음 (별도 처리 필요하지만 여기선 RGB 값만)
        'red': [255, 0, 0],
        'green': [0, 128, 0],
        'blue': [0, 0, 255]
    }
    if color_str in named_colors:
        return named_colors[color_str]

    # 2. Hex Colors (#RRGGBB or #RGB 처리)
    if color_str.startswith('#'):
        hex_code = color_str.lstrip('#')
        # #RGB -> #RRGGBB 변환
        if len(hex_code) == 3:
            hex_code = ''.join([c*2 for c in hex_code])
        if len(hex_code) == 6:
            try:
                return [int(hex_code[i:i+2], 16) for i in (0, 2, 4)]
            except ValueError:
                pass # 파싱 실패 시 아래 로직으로 이동

    # 3. rgb/rgba regex 파싱
    nums = re.findall(r"(\d+(?:\.\d+)?)", color_str)
    if len(nums) >= 3:
        return [float(n) for n in nums[:3]] # Alpha 값은 무시하고 R, G, B만 사용
    
    return [0, 0, 0] # 파싱 실패 시 기본값 (검정)

def get_luminance(rgb):
    """
    WCAG 2.1 정의에 따른 상대적 휘도(Relative Luminance)를 계산합니다.
    
    공식:
    L = 0.2126 * R + 0.7152 * G + 0.0722 * B
    (각 RGB 값은 sRGB 공간에서 선형화된 값으로 변환 후 계산)
    
    Args:
        rgb (list): [r, g, b] (0~255 범위)
        
    Returns:
        float: 0.0 (가장 어두움) ~ 1.0 (가장 밝음)
    """
    colors = []
    for c in rgb:
        c /= 255.0
        if c <= 0.03928:
            colors.append(c / 12.92)
        else:
            colors.append(((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * colors[0] + 0.7152 * colors[1] + 0.0722 * colors[2]

def get_contrast_ratio(rgb1, rgb2):
    """
    두 색상 간의 명암비(Contrast Ratio)를 계산합니다.
    WCAG 접근성 기준 검사에 핵심적으로 사용됩니다.
    
    공식: (L1 + 0.05) / (L2 + 0.05) (L1이 더 밝은 색의 휘도)
    
    Args:
        rgb1, rgb2 (list): [r, g, b] 색상 값
        
    Returns:
        float: 1.0 ~ 21.0 사이의 명암비
    """
    l1 = get_luminance(rgb1)
    l2 = get_luminance(rgb2)
    brightest = max(l1, l2)
    darkest = min(l1, l2)
    return (brightest + 0.05) / (darkest + 0.05)

def parse_css_size(value_str):
    """
    CSS 크기 문자열(예: 10px, 1.5rem)을 파싱하여 픽셀(px) 단위 float로 변환합니다.
    
    변환 규칙:
    - px: 숫자만 추출하여 반환
    - rem, em: 16px 기준으로 변환 (1rem = 16px 가정)
    - 기타 단위(%, vh 등) 또는 파싱 불가: 0.0 반환 (크기 비교에서 제외하기 위함)
    
    Args:
        value_str (str): CSS 크기 문자열
        
    Returns:
        float: 픽셀 단위 크기 또는 0.0
    """
    if not value_str or not isinstance(value_str, str):
        return 0.0
    
    value_str = value_str.lower().strip()
    if not value_str:
        return 0.0

    # 1. px 단위 처리
    if value_str.endswith("px"):
        try:
            return float(value_str.replace("px", ""))
        except ValueError:
            return 0.0
            
    # 2. rem / em 단위 처리 (Root font size 16px 기준)
    if value_str.endswith("rem") or value_str.endswith("em"):
        try:
            val = float(value_str.replace("rem", "").replace("em", ""))
            return val * 16.0
        except ValueError:
            return 0.0
            
    # 3. 단위 없는 숫자 (드물지만 처리)
    if re.match(r"^\d+(\.\d+)?$", value_str):
        try:
            return float(value_str)
        except ValueError:
            return 0.0

    return 0.0

def check_accessibility(json_path=None, data=None):
    """
    '첫눈에 보는(At First Glance)' 명확성 및 행동 유도성 체크리스트를 실행합니다.
    
    평가 항목 구분:
    A. 학습 용이성 (Learnability):
       - 시맨틱/속성: 표준 태그, role, tabindex, 레이블 존재 여부
       - 시각적 규칙: 커서, 크기, 명암비, 배경 대비, 비활성 상태 구분
    B. 통제 및 자유 (Control):
       - 시스템 상태 가시성: 페이지 제목, 현재 위치, 선택 상태 표시
    
    Args:
        json_path (str, optional): 분석할 요소 데이터가 담긴 JSON 파일 경로.
        data (dict, optional): 분석할 데이터 딕셔너리 (json_path 대신 직접 데이터 객체 전달 시 사용).
    
    Returns:
        dict: 분석 결과가 포함된 딕셔너리
    """
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

    # 결과 저장을 위한 구조 표준화
    json_results = {
        "url": url,
        "learnability": {"score": 0, "items": []},
        "efficiency": {"score": 0, "items": []},
        "control": {"score": 0, "items": []},
        "node_id": data.get("node_id")
    }

    # 카테고리별 통계
    learn_stats = {"passed": 0, "failed": 0}
    ctrl_stats = {"passed": 0, "failed": 0}
    
    has_breadcrumb = False

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
        
        # 요소 식별 정보
        element_info = {
            "tag": tag,
            "text": text,
            "id": el.get('id'),
            "class": el.get('class'),
            "type": el_type
        }

        # 카테고리별 체크 리스트
        checks_learn = []
        checks_ctrl = []
        
        status_learn = "PASS"
        status_ctrl = "PASS"

        # =========================================================
        # A. 학습 용이성 (Learnability) Checks
        # =========================================================
        
        # [표준 태그 사용 여부]
        if el_type in ["button", "button_custom", "link"]:
            check_name = "표준 태그 사용"
            if el_type == "button" and tag not in ["button", "input"]:
                checks_learn.append({"name": check_name, "status": "FAIL", "message": f"버튼 용도로 비표준 태그 <{tag}> 사용됨"})
                status_learn = "FAIL"
            elif el_type == "link" and tag != "a":
                checks_learn.append({"name": check_name, "status": "FAIL", "message": f"링크 용도로 비표준 태그 <{tag}> 사용됨"})
                status_learn = "FAIL"
            else:
                checks_learn.append({"name": check_name, "status": "PASS", "message": f"표준 태그 <{tag}> 사용됨"})

            # [커스텀 버튼 속성 검사]
            if tag in ["div", "span"]:
                check_name = "커스텀 버튼 접근성 속성"
                issues = []
                if role != "button": issues.append("role='button' 누락")
                if not tabindex or tabindex == "-1": issues.append("tabindex 누락 또는 잘못됨")
                
                if issues:
                    checks_learn.append({"name": check_name, "status": "FAIL", "message": ", ".join(issues)})
                    status_learn = "FAIL"
                else:
                    checks_learn.append({"name": check_name, "status": "PASS", "message": "필수 접근성 속성 존재"})

        # [텍스트/레이블 존재 여부]
        if el_type in ["button", "button_custom"]:
            check_name = "레이블(텍스트) 제공"
            actual_text = el.get('text', '').strip()
            if not actual_text and not aria_label and not title:
                checks_learn.append({"name": check_name, "status": "FAIL", "message": "텍스트나 대체 텍스트(aria-label 등)가 없음"})
                status_learn = "FAIL"
            else:
                checks_learn.append({"name": check_name, "status": "PASS", "message": "레이블 존재함"})

        # [시각적 규칙 검사]
        if el_type in ["button", "button_custom", "link"]:
            is_disabled = el.get('disabled', False)
            
            # [비활성화 상태 시각적 구분]
            if disabled_styles and el_type != "input":
                check_name = "비활성화 상태 시각적 구분"
                diff_found = False
                for prop in ["backgroundColor", "opacity", "color", "border"]:
                    if styles.get(prop) != disabled_styles.get(prop):
                        diff_found = True
                        break
                
                if is_disabled:
                    if styles.get('cursor') != 'not-allowed' and float(styles.get('opacity', '1') or '1') >= 1:
                        checks_learn.append({"name": check_name, "status": "FAIL", "message": "비활성화 상태임에도 시각적 구분(커서/투명도 등)이 부족함"})
                        status_learn = "FAIL"
                    else:
                        checks_learn.append({"name": check_name, "status": "PASS", "message": "비활성화 상태가 시각적으로 명확함"})
                elif not diff_found:
                     checks_learn.append({"name": check_name, "status": "INFO", "message": "비활성 스타일이 별도로 감지되지 않음"})
                else:
                     checks_learn.append({"name": check_name, "status": "PASS", "message": "비활성 스타일 정의됨"})

            # [Cursor Check]
            check_name = "마우스 커서 스타일"
            cursor = styles.get("cursor")
            if is_disabled:
                if cursor == "pointer":
                    checks_learn.append({"name": check_name, "status": "FAIL", "message": "비활성 요소에 'pointer' 커서가 사용됨"})
                    status_learn = "FAIL"
                else:
                    checks_learn.append({"name": check_name, "status": "PASS", "message": "적절한 커서 사용됨"})
            else:
                if cursor == "not-allowed":
                    checks_learn.append({"name": check_name, "status": "FAIL", "message": "활성 요소에 'not-allowed' 커서가 사용됨"})
                    status_learn = "FAIL"
                elif cursor != "pointer":
                    checks_learn.append({"name": check_name, "status": "FAIL", "message": f"커서가 'pointer'가 아님 ('{cursor}')"})
                    status_learn = "FAIL"
                else:
                    checks_learn.append({"name": check_name, "status": "PASS", "message": "커서 스타일 적절함"})

            # [Size Check]
            check_name = "터치 타겟 크기"
            width = rect.get('width', 0) if rect else 0
            height = rect.get('height', 0) if rect else 0
            if width <= 0 or height <= 0:
                width = parse_css_size(styles.get("width"))
                height = parse_css_size(styles.get("height"))

            if width < 24 or height < 24:
                checks_learn.append({"name": check_name, "status": "FAIL", "message": f"크기가 너무 작음: {int(width)}x{int(height)}px (최소 24px 권장)"})
                status_learn = "FAIL"
            else:
                checks_learn.append({"name": check_name, "status": "PASS", "message": f"크기 적절함 ({int(width)}x{int(height)}px)"})

            # [Color Contrast]
            check_name = "텍스트 명암비(가독성)"
            btn_bg = parse_color(styles.get("backgroundColor"))
            btn_text = parse_color(styles.get("color"))
            
            # 배경이 투명한 경우 부모 배경색 사용
            # bg_for_contrast = btn_bg
            # check_msg_suffix = ""
            
            # 투명 여부 확인 (alpha channel or 'transparent' keyword handled by parse_color returning [0,0,0] usually, 
            # but we need to check the raw style string or if parse_color handles alpha)
            # parse_color stub implementation currently returns [r,g,b], ignoring alpha unless we improve it.
            # safe check: check style string
            bg_style = styles.get("backgroundColor", "").lower()
            is_transparent = bg_style == 'transparent' or 'rgba(0, 0, 0, 0)' in bg_style
            if is_transparent:
                bg_for_contrast = parse_color(el.get("parent_backgroundColor"))
                check_msg_suffix = " (투명 배경, 부모 배경색 기준)"
            else:
                bg_for_contrast = btn_bg
                check_msg_suffix = ""

            contrast_text = get_contrast_ratio(bg_for_contrast, btn_text)
            
            if contrast_text < 4.5:
                checks_learn.append({"name": check_name, "status": "FAIL", "message": f"대비가 낮음: {contrast_text:.2f}:1 (최소 4.5:1 권장){check_msg_suffix}"})
                status_learn = "FAIL"
            else:
                checks_learn.append({"name": check_name, "status": "PASS", "message": f"대비 적절함 ({contrast_text:.2f}:1){check_msg_suffix}"})

            # [Visibility against Background]
            check_name = "배경 대비 가시성"
            parent_bg = parse_color(el.get("parent_backgroundColor"))
            if styles.get("backgroundColor") != "rgba(0, 0, 0, 0)" and "transparent" not in styles.get("backgroundColor", ""):
                contrast_container = get_contrast_ratio(btn_bg, parent_bg)
                if contrast_container < 3.0:
                    checks_learn.append({"name": check_name, "status": "FAIL", "message": f"배경과 구분이 잘 안됨: {contrast_container:.2f}:1 (최소 3.0:1 권장)"})
                    status_learn = "FAIL"
                else:
                    checks_learn.append({"name": check_name, "status": "PASS", "message": "배경과 구분 명확함"})

        # =========================================================
        # B. 통제 및 자유 (Control) Checks
        # =========================================================

        # [페이지 제목 (Heading) 확인]
        if el_type == 'heading':
            check_name = "페이지 제목(Heading)"
            if not text:
                checks_ctrl.append({"name": check_name, "status": "FAIL", "message": f"헤딩 태그 <{tag}> 내용이 비어있음"})
                status_ctrl = "FAIL"
            else:
                checks_ctrl.append({"name": check_name, "status": "PASS", "message": f"헤딩 존재함: '{text}'"})

        # [현재 위치 표시 (Current Page Indicator)]
        aria_current = el.get('aria_current')
        if aria_current and aria_current != 'false':
            check_name = "현재 위치 표시"
            checks_ctrl.append({"name": check_name, "status": "PASS", "message": f"현재 페이지임을 명시함 (aria-current='{aria_current}')"})
            
        # [선택 상태 표시 (Selection State)]
        is_selected = el.get('aria_selected') == 'true' or el.get('checked') is True or el.get('aria_pressed') == 'true'
        if is_selected:
            check_name = "선택/상태 표시"
            checks_ctrl.append({"name": check_name, "status": "PASS", "message": "요소가 선택/체크된 상태임"})
            # 통제 관련 요소가 하나라도 있으면 PASS로 칠 수도 있지만, 여기서는 개별 체크 결과를 저장
        
        # [Breadcrumb Check]
        if tag == 'nav' and (aria_label == 'breadcrumb' or 'breadcrumb' in (el.get('class') or '').lower()):
            has_breadcrumb = True
            checks_ctrl.append({"name": "이동 경로(Breadcrumb)", "status": "PASS", "message": "Breadcrumb 제공됨"})
        
        # ---------------------------------------------------------
        # 결과 집계 (Standardized format: Grouped by element)
        # ---------------------------------------------------------
        if checks_learn:
            json_results["learnability"]["items"].append({
                "element": element_info,
                "checks": checks_learn
            })
            for c in checks_learn:
                if c["status"] == "FAIL": learn_stats["failed"] += 1
                else: learn_stats["passed"] += 1

        if checks_ctrl:
            json_results["control"]["items"].append({
                "element": element_info,
                "checks": checks_ctrl
            })
            for c in checks_ctrl:
                if c["status"] == "FAIL": ctrl_stats["failed"] += 1
                else: ctrl_stats["passed"] += 1

    # [Global Checks]
    if not has_breadcrumb:
        json_results["control"]["items"].append({
            "element": {"tag": "Page", "text": "Global Check", "type": "page"},
            "checks": [{"name": "이동 경로(Breadcrumb)", "status": "FAIL", "message": "Breadcrumb(이동 경로)가 제공되지 않음"}]
        })
        ctrl_stats["failed"] += 1
    else:
        json_results["control"]["items"].append({
            "element": {"tag": "Page", "text": "Global Check", "type": "page"},
            "checks": [{"name": "이동 경로(Breadcrumb)", "status": "PASS", "message": "Breadcrumb 제공됨"}]
        })
        ctrl_stats["passed"] += 1

    # 점수 계산 (항목별 통과율 기반)
    def calculate_score(stats):
        total = stats["passed"] + stats["failed"]
        return round((stats["passed"] / total * 100), 1) if total > 0 else 100.0

    json_results["learnability"]["score"] = calculate_score(learn_stats)
    json_results["control"]["score"] = calculate_score(ctrl_stats)
    # Efficiency는 이 모듈에서 다루지 않으므로 100점(또는 N/A) 처리
    json_results["efficiency"]["score"] = 100.0

    # ---------------------------------------------------------
    # 터미널 출력 (간단 요약)
    # ---------------------------------------------------------
    print(f"\n[Summary]")
    print(f"Learnability - 통과: {learn_stats['passed']}, 실패: {learn_stats['failed']} (Score: {json_results['learnability']['score']})")
    print(f"Control      - 통과: {ctrl_stats['passed']}, 실패: {ctrl_stats['failed']} (Score: {json_results['control']['score']})")

    # JSON 파일 저장
    if json_path:
        output_path = os.path.join(os.path.dirname(json_path), "checklist_results.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(json_results, f, indent=2, ensure_ascii=False)
        print(f"\n--- 결과가 저장되었습니다: {output_path} ---")

    return json_results

if __name__ == "__main__":
    json_file_path = os.path.join(os.path.dirname(__file__), "..", "elements.json")
    check_accessibility(json_file_path)
