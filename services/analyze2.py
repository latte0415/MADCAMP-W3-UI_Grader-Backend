### 여러 개의 actions가 주어짐.


import sys
import os
import argparse
from uuid import UUID

# Import path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from services.node import NodeAnalyzer
    from services.edge_service import get_edge_by_id
    from services.element_extractor import ElementExtractor
    from evaluators.doing_actions.doing_actions import evaluate_doing_actions
except ImportError:
    # Fallback if running directly from services/
    sys.path.append(project_root)
    from services.node import NodeAnalyzer
    from services.edge_service import get_edge_by_id
    from services.element_extractor import ElementExtractor
    from evaluators.doing_actions.doing_actions import evaluate_doing_actions

def analyze_workflow(edge_ids, chain_data=None):
    """
    워크플로우(액션 체인) 분석 수행.
    chain_data가 제공되면 데이터 로딩을 건너뜁니다.
    """
    if chain_data:
        print(f"이미 처리된 데이터를 사용합니다: {len(chain_data)} steps")
    else:
        print(f"Analyzing chain of {len(edge_ids)} edges...")
        chain_data = []
        previous_to_node_id = None

        for i, edge_id in enumerate(edge_ids):
            step_data = {}
            print(f"\n{'='*20} Step {i+1} : Edge {edge_id} {'='*20}")
            
            # 1. Load Action (Edge)
            edge_data = get_edge_by_id(edge_id)
            if not edge_data:
                print(f"[ERROR] Failed to load Edge data for ID: {edge_id}")
                previous_to_node_id = None 
                continue
            
            step_data['action'] = edge_data

            from_node_id = edge_data.get('from_node_id')
            to_node_id = edge_data.get('to_node_id')

            # Check continuity
            if previous_to_node_id and from_node_id != previous_to_node_id:
                print(f"[WARNING] Discontinuity detected! Previous To-Node ({previous_to_node_id}) != Current From-Node ({from_node_id})")

            print(f"[Edge Info]")
            print(f"  ID:      {edge_id}")
            
            # 2. Load Previous Node
            if from_node_id:
                print(f"\n[From Node] {from_node_id}")
                prev_node = NodeAnalyzer(from_node_id)
                if prev_node.load_data():
                    # Extract Elements
                    prev_data = prev_node.node_data if prev_node.node_data else {}
                    prev_dom = prev_node.get_dom()
                    prev_css = prev_node.get_css()
                    
                    if prev_dom:
                        print(f"  - Extracting elements from DOM ({len(prev_dom)} chars)...")
                        extractor = ElementExtractor(prev_dom, prev_css)
                        extraction_result = extractor.extract()
                        prev_data["elements"] = extraction_result.get("elements", [])
                        prev_data["status_components"] = extraction_result.get("status_components", {})
                        print(f"  - Extracted {len(prev_data['elements'])} elements.")
                    
                    step_data['from_node'] = prev_data
                else:
                    print("  [ERROR] Failed to load From Node data")
                    step_data['from_node'] = None
            else:
                print("\n[From Node] None")
                step_data['from_node'] = None

            # 3. Load Next Node
            if to_node_id:
                print(f"\n[To Node] {to_node_id}")
                next_node = NodeAnalyzer(to_node_id)
                if next_node.load_data():
                    next_data = next_node.node_data if next_node.node_data else {}
                    step_data['to_node'] = next_data
                else:
                    print("  [ERROR] Failed to load To Node data")
                    step_data['to_node'] = None
            else:
                print("\n[To Node] None")
                step_data['to_node'] = None
            
            chain_data.append(step_data)
            previous_to_node_id = to_node_id
    
    print(f"\n{'='*20} Analysis Complete. Passing to Doing Actions Evaluator... {'='*20}")
    return evaluate_doing_actions(chain_data)

def main():
    parser = argparse.ArgumentParser(description="Analyze a chain of edges.")
    parser.add_argument("edge_ids", nargs='+', help="List of Edge UUIDs in order")
    
    args = parser.parse_args()
    analyze_workflow(args.edge_ids)

if __name__ == "__main__":
    main()