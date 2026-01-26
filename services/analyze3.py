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

def main():
    parser = argparse.ArgumentParser(description="Analyze transition between two nodes using Edge ID.")
    parser.add_argument("edge_id", help="Edge (Action) UUID to analyze")
    
    args = parser.parse_args()

    print(f"--- Analyzing Transition for Edge: {args.edge_id} ---")

    # 1. Load Action (Edge)
    print("\n[1] Loading Action (Edge)...")
    edge_data = get_edge_by_id(args.edge_id)
    if not edge_data:
        print(f"[ERROR] Failed to load Edge data for ID: {args.edge_id}")
        return

    print(f"Action Type: {edge_data.get('action_type')}")
    print(f"Target:      {edge_data.get('action_target')}")
    print(f"Value:       {edge_data.get('action_value')}")
    print(f"Outcome:     {edge_data.get('outcome')}")
    
    from_node_id = edge_data.get('from_node_id')
    to_node_id = edge_data.get('to_node_id')

    print(f"Previous Node ID: {from_node_id}")
    print(f"Next Node ID:     {to_node_id}")
    print("-" * 30)

    # 2. Load Previous Node
    if from_node_id:
        print(f"\n[2] Loading Previous Node ({from_node_id})...")
        prev_node = NodeAnalyzer(from_node_id)
        if prev_node.load_data():
            prev_node.print_summary()
        else:
            print("[ERROR] Failed to load Previous Node.")
    else:
        print("\n[2] Previous Node ID is missing in Edge data.")

    # 3. Load Next Node
    if to_node_id:
        print(f"\n[3] Loading Next Node ({to_node_id})...")
        next_node = NodeAnalyzer(to_node_id)
        if next_node.load_data():
            next_node.print_summary()
        else:
            print("[ERROR] Failed to load Next Node.")
    else:
        print("\n[3] Next Node ID is missing in Edge data.")
        
    print("\n--- Load Complete ---")

    # 4. Evaluate Visibility of System Status
    if edge_data and prev_node and next_node:
        print("\n--- Evaluating Visibility of System Status ---")
        try:
            from evaluators.after_actions.after_actions import evaluate_after_action
            from services.element_extractor import ElementExtractor
            
            # Prepare data dictionaries
            prev_data = prev_node.node_data if prev_node.node_data else {}
            next_data = next_node.node_data if next_node.node_data else {}

            # Perform Element Extraction for Previous Node
            prev_dom = prev_node.get_dom()
            prev_css = prev_node.get_css()
            
            if prev_dom:
                print("\n[ElementExtractor] Extracting elements from Previous Node...")
                extractor = ElementExtractor(prev_dom, prev_css)
                extraction_result = extractor.extract()
                prev_data["elements"] = extraction_result.get("elements", [])
                prev_data["status_components"] = extraction_result.get("status_components", {})
                print(f"  - Cleaned up {len(prev_data['elements'])} extracted elements.")
            
            results = evaluate_after_action(edge_data, prev_data, next_data)
            
            print("\n[Efficiency Result]")
            eff = results.get("efficiency", {})
            lat = eff.get("latency", {})
            print(f"  - Latency: {lat.get('duration_ms')}ms")
            print(f"  - Status:  {lat.get('status')}")
            print(f"  - Desc:    {lat.get('description')}")
            
            print("\n[Control Result]")
            ctrl = results.get("control", {})
            fb = ctrl.get("immediate_feedback", {})
            print(f"  - Feedback Status: {fb.get('status')}")
            print(f"  - Description:     {fb.get('description')}")
            
            vis = ctrl.get("visibility_of_status", {})
            print(f"  - Context:         {vis.get('description')}")
            
        except ImportError as e:
            print(f"[ERROR] Could not import evaluator: {e}")
        except Exception as e:
            print(f"[ERROR] Evaluation failed: {e}")
    else:
        print("\n[SKIP] Cannot evaluate: Missing edge or node data.")

if __name__ == "__main__":
    main()