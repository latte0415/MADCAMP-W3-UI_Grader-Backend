from typing import Dict, Any

def evaluate_after_action(edge_data: Dict[str, Any], prev_node_data: Dict[str, Any], next_node_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    시스템 상태 가시성 (Control & Efficiency) 평가 함수.
    
    Args:
        edge_data: 상호작용 데이터 (지연 시간, 액션 타입, 결과 등)
        prev_node_data: 상호작용 전의 노드 데이터
        next_node_data: 상호작용 후의 노드 데이터
        
    Returns:
        Control 및 Efficiency 평가 결과가 포함된 딕셔너리.
    """
    results = {
        "learnability": {"score": 0.0, "passed": [], "failed": []},
        "efficiency": {
            "score": 0, 
            "passed": [], 
            "failed": [],
            "latency": {"duration_ms": 0, "status": "Unknown", "description": ""}
        },
        "control": {"score": 0, "passed": [], "failed": []}
    }

    # 1. 효율성(Efficiency): 시스템 지연 시간 및 반응성
    latency = edge_data.get('latency_ms', 0)
    results["efficiency"]["latency"]["duration_ms"] = latency
    
    # Helper to find action element in prev_node_data
    def find_action_element(target: str, elements: list) -> dict:
        """
        이전 노드의 요소 목록에서 사용자가 상호작용한 대상 요소를 찾습니다.
        
        Args:
            target (str): 상호작용 대상 텍스트 또는 식별자 (예: "role=button name=로그인")
            elements (list): 이전 노드의 인터랙티브 요소 목록
            
        Returns:
            dict: 찾은 요소 정보 또는 None
        """
        if not target: return None
        
        # 1. Parse target string if it follows "prop=value" format
        target_name = target
        if "name=" in target:
            import re
            match = re.search(r'name=(.*?)(?:\s|$)', target)
            if match:
                target_name = match.group(1).strip()
        
        # 2. Search in elements
        for el in elements:
            # Prepare accessible name of element
            el_text = (el.get('text') or "").strip()
            el_aria = (el.get('aria_label') or "").strip()
            el_title = (el.get('title') or "").strip()
            
            # Check for exact or partial match with the extracted name
            if target_name in el_text or target_name in el_aria or target_name in el_title:
                return el
                
            # Fallback: Check original target string against class/id (legacy support)
            if target.startswith('.') and target[1:] in el.get('class', ''):
                return el
            if target.startswith('#') and target[1:] == el.get('id'):
                return el
                
        return None

    # Helper to check if two rects represent the same element (Strict)
    def is_same_element(rect1, rect2):
        if not rect1 or not rect2: return False
        # Allow small margin of error
        return (abs(rect1['x'] - rect2['x']) < 5 and 
                abs(rect1['y'] - rect2['y']) < 5 and
                abs(rect1['width'] - rect2['width']) < 5 and
                abs(rect1['height'] - rect2['height']) < 5)

    # 지연 시간 임계값 기준
    found_relevant_indicator = False
    
    if latency < 200:
        results["efficiency"]["latency"]["status"] = "Excellent"
        results["efficiency"]["latency"]["description"] = "반응이 매우 빠릅니다 (200ms 미만). 즉각적이라고 느껴집니다."
    elif latency < 1000:
        results["efficiency"]["latency"]["status"] = "Good"
        results["efficiency"]["latency"]["description"] = "반응이 양호합니다 (1초 미만). 사용자의 사고 흐름이 끊기지 않습니다."
    else:
        results["efficiency"]["latency"]["status"] = "Slow"
        desc = f"반응이 느립니다 ({latency}ms). "
        
        # 느릴 경우 로딩 UI나 진행 표시가 있었는지 확인
        status_comps = prev_node_data.get("status_components", {})
        progress_indicators = status_comps.get("progress_indicators", [])
        
        action_target = edge_data.get('action_target') # e.g., text of the clicked element
        elements = prev_node_data.get('elements', []) # All elements from the previous node
        
        if progress_indicators:
            action_el = find_action_element(action_target, elements)
            
            if action_el:
                action_rect = action_el.get('rect')
                for prog in progress_indicators:
                    # 1. Container Match (extracted from DOM hierarchy)
                    container = prog.get('container')
                    if container:
                        if is_same_element(action_rect, container.get('rect')):
                             found_relevant_indicator = True
                             desc += "(버튼 내부 로딩-위치 일치) "
                             break
                        # 텍스트가 일치하는 경우도 고려
                        if action_target and action_target in container.get('text', ''):
                             found_relevant_indicator = True
                             desc += "(버튼 내부 로딩-텍스트 일치) "
                             break
                    
                    
                    # 3. Proximity check (Distance-based)
                    # if the indicator is visually close to the button (e.g. < 100px)
                    prog_rect = prog.get('rect')
                    if not found_relevant_indicator and action_rect and prog_rect:
                        # Calculate center of button
                        btn_cx = action_rect['x'] + action_rect['width'] / 2
                        btn_cy = action_rect['y'] + action_rect['height'] / 2
                        
                        # Calculate center of indicator
                        prog_cx = prog_rect['x'] + prog_rect['width'] / 2
                        prog_cy = prog_rect['y'] + prog_rect['height'] / 2
                        
                        # Euclidean distance
                        import math
                        distance = math.sqrt((btn_cx - prog_cx)**2 + (btn_cy - prog_cy)**2)
                        
                        # Threshold: 100px (heuristic)
                        if distance < 100: # Slightly generous 100px to cover side-by-side layouts
                             found_relevant_indicator = True
                             desc += f"(버튼과 근접한 로딩 감지: 거리 {int(distance)}px) "
                             break

                if found_relevant_indicator:
                    desc += "이전 화면에서 클릭한 요소와 연관된 진행 표시기가 감지되어, 사용자에게 적절한 피드백을 제공했을 가능성이 높습니다."
                else:
                    desc += "진행 표시기가 감지되었으나, 클릭한 버튼(작업 대상)과 거리가 멀어 연관성을 확신할 수 없습니다."
            else:
                 # Action target not found in elements list
                 desc += "진행 표시기가 감지되었으나, 작업 대상 요소의 위치를 파악할 수 없어 연관성을 확신할 수 없습니다."
        else:
             desc += "사용자가 기다려야 하는 이유를 알 수 있는 로딩 UI나 진행 상태 표시가 필요합니다."
        
        results["efficiency"]["latency"]["description"] = desc

    # 2. 통제성(Control): 시스템 상태의 가시성 (피드백)
    # 내 행동이 처리되었는지 즉시 알 수 있는가?
    # 로딩, 처리 중, 완료, 실패가 명확히 구분되는가?
    


    # (2) 상태 구분 및 가시성
    if latency >= 1000:
        if found_relevant_indicator:
            results["control"]["passed"].append({
                "check": "Visibility of Status",
                "message": "작업 시간이 길었지만, 적절한 진행 표시(로딩 등)가 제공되었습니다."
            })
        else:
            results["control"]["failed"].append({
                "check": "Visibility of Status",
                "message": "작업 시간이 길었음에도 '처리 중'임을 나타내는 명확한 지표(로딩 등)를 찾기 어렵습니다."
            })
    else:
        results["control"]["passed"].append({
            "check": "Visibility of Status",
            "message": "작업이 신속히 처리되어 즉각적으로 상태가 전환되었습니다."
        })

    # (3) 효율성 (지연 시간)
    if latency < 1000:
        results["efficiency"]["passed"].append({
            "check": "System Latency",
            "message": f"지연 시간({latency}ms)이 1초 미만으로 양호합니다."
        })
    else:
        results["efficiency"]["failed"].append({
            "check": "System Latency",
            "message": f"지연 시간({latency}ms)이 1초 이상으로 느립니다."
        })

    # 점수 계산
    def calculate_score(cat):
        total = len(cat["passed"]) + len(cat["failed"])
        return round((len(cat["passed"]) / total * 100), 1) if total > 0 else 100.0

    results["efficiency"]["score"] = calculate_score(results["efficiency"])
    results["control"]["score"] = calculate_score(results["control"])

    return results
