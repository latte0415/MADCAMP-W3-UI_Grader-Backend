from typing import List, Dict, Any, Optional
import math

def evaluate_doing_actions(chain_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    행동 체인의 효율성(상호작용 효율성, 목표 크기 및 간격)을 평가합니다.
    """
    print(f"\n[{__file__}] {len(chain_data)} 단계에 대한 효율성 평가 중...")
    
    results = {
        "efficiency": {
            "interaction_efficiency": {
                "total_estimated_time_s": 0.0,
                "klm_breakdown": [],
                "step_count": len(chain_data),
                "comments": []
            },
            "target_size_spacing": {
                "fitts_issues": [],
                "size_issues": [],
                "comments": []
            }
        }
    }

    # KLM 연산자 (초 단위 근사값)
    # K (Keystroke): 0.2s (평균 타자 속도)
    # P (Pointing/Mouse to target): 1.1s (목표지점까지 포인팅/마우스 이동)
    # H (Homing/Switch device): 0.4s (손을 키보드/마우스로 이동)
    # M (Mental preparation): 1.35s (정신적 준비)
    # B (Button click): 0.1s (버튼 클릭)
    KLM_OPS = {
        "K": 0.2, 
        "P": 1.1,
        "H": 0.4,
        "M": 1.35,
        "B": 0.1
    }

    # 더 나은 휴리스틱: 0단계의 경우 거리를 무시하거나 화면 중앙(1920/2, 1080/2)을 가정.
    last_pos = {"x": 960, "y": 540} 

    total_klm_time = 0.0

    for i, step in enumerate(chain_data):
        action = step.get('action', {})
        from_node = step.get('from_node', {}) or {}
        elements = from_node.get('elements', [])
        
        action_type = action.get('action_type')
        action_target = action.get('action_target')
        action_value = action.get('action_value')
        
        # --- 1. 상호작용 효율성 (KLM) ---
        step_time = 0.0
        step_ops = []
        
        # 간단한 KLM 휴리스틱 매핑
        if action_type == "click":
            # M (정신적 준비) + P (포인팅) + B (클릭 해제)
            step_ops = ["M", "P", "B"]
            step_time = KLM_OPS["M"] + KLM_OPS["P"] + KLM_OPS["B"]
            
        elif action_type == "fill" or action_type == "type":
            # M (정신적 준비) + P (입력창 포인팅) + B (클릭) + H (키보드로 손 이동) + K * 길이
            text_len = len(str(action_value)) if action_value else 0
            step_ops = ["M", "P", "B", "H"] + ["K"] * text_len
            step_time = KLM_OPS["M"] + KLM_OPS["P"] + KLM_OPS["B"] + KLM_OPS["H"] + (KLM_OPS["K"] * text_len)
            
        elif action_type == "hover":
            # M (정신적 준비) + P (포인팅)
            step_ops = ["M", "P"]
            step_time = KLM_OPS["M"] + KLM_OPS["P"]
            
        elif action_type == "navigate":
            # 주로 시스템 응답, 아마도 M (정신적 준비)
            step_ops = ["M"]
            step_time = KLM_OPS["M"]
            
        else:
            # 기본 대체값
            step_ops = ["M"]
            step_time = KLM_OPS["M"]

        total_klm_time += step_time
        results["efficiency"]["interaction_efficiency"]["klm_breakdown"].append({
            "step": i,
            "action": action_type,
            "ops": step_ops,
            "est_time": round(step_time, 2)
        })

        # --- 2. 목표 크기 및 간격 (Fitts의 법칙) ---
        target_el = find_element(action_target, elements)
        
        if target_el and target_el.get('rect'):
            rect = target_el['rect']
            cx = rect['x'] + rect['width'] / 2
            cy = rect['y'] + rect['height'] / 2
            
            # (A) 크기 확인
            # Apple HIG: 44x44pt, Android: 48x48dp, WCAG: 24x24 (최소)
            # 엄격한 평가자를 위해 엄격하게 기준 설정: 32px 미만이면 경고
            min_dim = min(rect['width'], rect['height'])
            if min_dim < 32:
                results["efficiency"]["target_size_spacing"]["size_issues"].append({
                    "step": i,
                    "target": action_target,
                    "size": f"{rect['width']}x{rect['height']}",
                    "message": "목표가 너무 작아(<32px) 정확하게 클릭하기 어렵습니다."
                })
            
            # (B) Fitts의 법칙
            # 마지막 위치로부터의 거리
            dist = math.sqrt((cx - last_pos['x'])**2 + (cy - last_pos['y'])**2)
            
            # Fitts의 법칙에서 너비(W)는 일반적으로 이동 축을 따른 목표의 크기입니다.
            # 유효 너비에 대한 보수적인 추정치로 min_dim을 사용합니다.
            w = max(min_dim, 1) # 0으로 나누기 방지
            
            # 난이도 지수 (ID) = log2(D/W + 1)
            fitts_id = math.log2(dist / w + 1)
            
            if fitts_id > 3.0: # "어려움"에 대한 휴리스틱 임계값
                results["efficiency"]["target_size_spacing"]["fitts_issues"].append({
                    "step": i,
                    "target": action_target,
                    "distance": round(dist, 1),
                    "width": w,
                    "ID": round(fitts_id, 2),
                    "message": "높은 난이도 지수 (먼 거리 또는 작은 목표)."
                })
            
            # 마지막 위치 업데이트
            last_pos = {"x": cx, "y": cy}
        else:
            # 탐색했거나 목표를 찾을 수 없는 경우, 현재 위치는 정의되지 않습니다.
            # last_pos를 유지할지 초기화할지? last_pos를 유지하는 것은 위험합니다.
            # 어디를 클릭했는지 모르면 다음 단계를 위한 거리(D)를 계산할 수 없습니다.
            pass

    results["efficiency"]["interaction_efficiency"]["total_estimated_time_s"] = round(total_klm_time, 2)

    
    print_efficiency_report(results)
    return results




def find_element(target: str, elements: List[Dict]) -> Optional[Dict]:
    """after_actions에 있는 것과 유사한 헬퍼 함수입니다."""
    if not target: return None
    
    # 간단한 휴리스틱 검색
    target_clean = target
    if "name=" in target:
        import re
        match = re.search(r'name=(.*?)(?:\s|$)', target)
        if match: target_clean = match.group(1)
        
    for el in elements:
        txt = (el.get('text') or "")
        aria = (el.get('aria_label') or "")
        if target_clean in txt or target_clean in aria:
            return el
            
    return None

def print_efficiency_report(results: Dict):
    eff = results["efficiency"]
    ie = eff["interaction_efficiency"]
    tss = eff["target_size_spacing"]
    
    print("\n" + "="*40)
    print("      [효율성 분석 보고서]      ")
    print("="*40)
    
    print(f"\n1. 상호작용 효율성 (KLM 모델)")
    print(f"   - 총 단계: {ie['step_count']}")
    print(f"   - 예상 작업 시간: {ie['total_estimated_time_s']}초")
    if ie['step_count'] > 5 and ie['total_estimated_time_s'] > 15:
        print("   - [팁] 워크플로우가 긴 것 같습니다. 단계를 줄이는 것을 고려하세요.")
    
    print(f"\n2. 목표 크기 및 간격 (Fitts의 법칙)")
    if not tss["size_issues"] and not tss["fitts_issues"]:
        print("   - 중대한 크기 또는 간격 문제가 감지되지 않았습니다. (좋음)")
    
    if tss["size_issues"]:
        print(f"   - [!] {len(tss['size_issues'])}개의 작은 목표 발견:")
        for issue in tss["size_issues"]:
            print(f"     * 단계 {issue['step']+1}: '{issue['target']}' 크기: {issue['size']} (권장: >32px)")
            
    if tss["fitts_issues"]:
        print(f"   - [!] {len(tss['fitts_issues'])}개의 높은 난이도 동작 발견 (ID > 3.0):")
        for issue in tss["fitts_issues"]:
            print(f"     * 단계 {issue['step']+1}: '{issue['target']}'(으)로 이동 (거리: {issue['distance']}px, ID: {issue['ID']})")


    print("="*40 + "\n")
