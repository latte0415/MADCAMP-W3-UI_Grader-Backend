## 3 행동 직후 (즉각적 피드백 단계)
### 한 개의 action이 주어진다고 가정


import sys
import os
import argparse
import json
from uuid import UUID

# Import path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from services.node import NodeAnalyzer
    from services.edge_service import get_edge_by_id
except ImportError:
    from node import NodeAnalyzer
    from edge_service import get_edge_by_id

def analyze_transition(edge_id, edge_data=None, prev_node_data=None, next_node_data=None):
    """
    이동(액션 직후 피드백) 분석 수행.
    데이터가 제공되면 로딩 및 요소 추출 과정을 건너뜁니다.
    """
    try:
        from evaluators.after_actions.after_actions import evaluate_after_action
        from services.element_extractor import ElementExtractor

        # Check if we have the minimum required data (edge and prev_node)
        if edge_data is not None and prev_node_data is not None:
            print(f"이미 처리된 데이터를 사용합니다: Edge {edge_id}")
        else:
            print(f"\n[1] Loading Action (Edge)...")
            edge_data = get_edge_by_id(edge_id)
            if not edge_data:
                print(f"[ERROR] Failed to load Edge data for ID: {edge_id}")
                return None

            from_node_id = edge_data.get('from_node_id')
            to_node_id = edge_data.get('to_node_id')

            # Load Previous Node
            if from_node_id:
                print(f"\n[2] Loading Previous Node ({from_node_id})...")
                prev_node = NodeAnalyzer(from_node_id)
                if prev_node.load_data():
                    prev_node_data = prev_node.node_data if prev_node.node_data else {}
                    prev_dom = prev_node.get_dom()
                    prev_css = prev_node.get_css()
                    if prev_dom:
                        print("\n[ElementExtractor] Extracting elements from Previous Node...")
                        extractor = ElementExtractor(prev_dom, prev_css)
                        extraction_result = extractor.extract()
                        prev_node_data["elements"] = extraction_result.get("elements", [])
                        prev_node_data["status_components"] = extraction_result.get("status_components", {})
                else:
                    print("[ERROR] Failed to load Previous Node.")
                    return None
            
            # Load Next Node (Optional)
            if to_node_id:
                print(f"\n[3] Loading Next Node ({to_node_id})...")
                next_node = NodeAnalyzer(to_node_id)
                if next_node.load_data():
                    next_node_data = next_node.node_data if next_node.node_data else {}
                else:
                    print("[ERROR] Failed to load Next Node.")
                    # We can still proceed even if next node fails to load,
                    # as evaluate_after_action mostly needs edge and prev_node.
                    next_node_data = {}

        if edge_data is not None and prev_node_data is not None:
            print("\n--- Evaluating Visibility of System Status ---")
            # next_node_data can be None or {}
            results = evaluate_after_action(edge_data, prev_node_data, next_node_data or {})
            
            eff = results.get("efficiency", {})
            lat = eff.get("latency", {})
            print(f"[Efficiency Result] Latency: {lat.get('duration_ms')}ms, Status: {lat.get('status')}")
            
            return results
        else:
            print("\n[SKIP] Cannot evaluate: Missing edge or previous node data.")
            return None

    except Exception as e:
        print(f"[ERROR] Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    parser = argparse.ArgumentParser(description="Analyze transition between two nodes using Edge ID.")
    parser.add_argument("edge_id", help="Edge (Action) UUID to analyze")
    
    args = parser.parse_args()
    print(f"--- Analyzing Transition for Edge: {args.edge_id} ---")
    analyze_transition(args.edge_id)

if __name__ == "__main__":
    main()