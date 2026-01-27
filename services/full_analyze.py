"""Full Analysis Orchestrator
한 개의 Run에 대해 정적 분석(Node), 전이 분석(Edge), 워크플로우 분석(DFS Paths)을 모두 수행합니다.
"""
import sys
import os
import json
import argparse
from uuid import UUID
from datetime import datetime

# 프로젝트 루트 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# 서비스 및 평가 모듈 임포트
from services.graph_service import get_run_graph_analysis
from services.node import NodeAnalyzer
from services.element_extractor import ElementExtractor
from evaluators.at_first_glance.at_first_glance import check_accessibility
from evaluators.after_actions.after_actions import evaluate_after_action
from evaluators.doing_actions.doing_actions import evaluate_doing_actions
from utils.logger import get_logger
from playwright.sync_api import sync_playwright

logger = get_logger(__name__)

def run_full_analysis(run_id: UUID):
    print(f"\n{'='*20} Start Full Analysis for Run: {run_id} {'='*20}")
    
    # 1. 그래프 데이터 및 DFS 경로 가져오기
    print("\n[1] Fetching Graph and DFS Paths...")
    graph_data = get_run_graph_analysis(run_id)
    nodes_raw = graph_data.get("nodes", [])
    edges_raw = graph_data.get("edges", [])
    paths_raw = graph_data.get("paths", [])
    
    print(f"  - Nodes: {len(nodes_raw)}")
    print(f"  - Edges: {len(edges_raw)}")
    print(f"  - Paths: {len(paths_raw)}")

    # 2. 노드 데이터 전처리 (Element Extraction)
    print("\n[2] Pre-processing Nodes (Element Extraction)...")
    node_cache = {} # node_id -> enriched_node_data
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for node in nodes_raw:
            node_id = str(node['id'])
            analyzer = NodeAnalyzer(node_id)
            if analyzer.load_data():
                dom = analyzer.get_dom()
                css = analyzer.get_css()
                
                node_data = analyzer.node_data.copy()
                if dom:
                    extractor = ElementExtractor(dom, css)
                    # Pass the shared page for optimization
                    extraction_result = extractor.extract(page=page)
                    node_data["elements"] = extraction_result.get("elements", [])
                    node_data["status_components"] = extraction_result.get("status_components", {})
                else:
                    node_data["elements"] = []
                    node_data["status_components"] = {}
                    
                node_cache[node_id] = node_data
                print(f"  - Node {node_id[:8]} processed ({len(node_data['elements'])} elements)")
            else:
                logger.warning(f"Failed to load data for node {node_id}")
        
        browser.close()

    # 3. 정적 분석 (At First Glance)
    print("\n[3] Running Static Analysis (Accessibility & Clarity)...")
    static_results = []
    from services.analyze import analyze_single_node
    
    for node_id, node_data in node_cache.items():
        try:
            eval_res = analyze_single_node(node_id=node_id, node_data=node_data)
            if eval_res:
                static_results.append({
                    "node_id": node_id,
                    "url": node_data.get("url"),
                    "result": eval_res
                })
        except Exception as e:
            logger.error(f"Static analysis failed for node {node_id}: {e}")

    # 4. 전이 분석 (After Action - Latency & Feedback)
    print("\n[4] Running Transition Analysis (Latency & Feedback)...")
    transition_results = []
    from services.analyze3 import analyze_transition
    
    for edge in edges_raw:
        edge_id = str(edge.get('id'))
        from_id = str(edge.get('from_node_id'))
        to_id = str(edge.get('to_node_id'))
        
        prev_data = node_cache.get(from_id, {})
        next_data = node_cache.get(to_id, {})
        
        try:
            eval_res = analyze_transition(edge_id=edge_id, edge_data=edge, prev_node_data=prev_data, next_node_data=next_data)
            if eval_res:
                transition_results.append({
                    "edge_id": edge_id,
                    "action": f"{edge.get('action_type')} on {edge.get('action_target')}",
                    "result": eval_res
                })
        except Exception as e:
            logger.error(f"Transition analysis failed for edge {edge_id}: {e}")

    # 5. 워크플로우 분석 (Doing Actions - Efficiency)
    print("\n[5] Running Workflow Analysis (Interaction Efficiency)...")
    workflow_results = []
    from services.analyze2 import analyze_workflow

    for i, path in enumerate(paths_raw):
        # path: {"nodes": [...], "edges": [...]}
        chain_data = []
        path_nodes = path.get("nodes", [])
        path_edges = path.get("edges", [])
        
        for j in range(len(path_edges)):
            from_node_id = str(path_nodes[j]['id'])
            to_node_id = str(path_nodes[j+1]['id']) if j+1 < len(path_nodes) else None
            
            chain_data.append({
                "action": path_edges[j],
                "from_node": node_cache.get(from_node_id),
                "to_node": node_cache.get(to_node_id) if to_node_id else None
            })
        
        try:
            eval_res = analyze_workflow(edge_ids=None, chain_data=chain_data)
            if eval_res:
                workflow_results.append({
                    "path_index": i,
                    "path_summary": " -> ".join([str(n['id'])[:8] for n in path_nodes]),
                    "result": eval_res
                })
        except Exception as e:
            logger.error(f"Workflow analysis failed for path {i}: {e}")

    # 6. 결과 통합 및 최종 점수 계산
    # 모든 노드/엣지/경로의 점수를 평균내어 최종 점수 산출
    
    def get_avg_score(results_list, category):
        scores = [r["result"][category]["score"] for r in results_list if "result" in r and category in r["result"]]
        return round(sum(scores) / len(scores), 1) if scores else 100.0

    l_score = get_avg_score(static_results, "learnability")
    # Efficiency는 After Action과 Doing Actions 모두에 영향 받음
    e_scores = [r["result"]["efficiency"]["score"] for r in transition_results] + \
               [r["result"]["efficiency"]["score"] for r in workflow_results]
    e_score = round(sum(e_scores) / len(e_scores), 1) if e_scores else 100.0
    
    c_score = get_avg_score(static_results + transition_results, "control")

    total_score = round((l_score + e_score + c_score) / 3, 1)

    final_output = {
        "run_id": str(run_id),
        "timestamp": datetime.now().isoformat(),
        "total_score": total_score,
        "category_scores": {
            "learnability": l_score,
            "efficiency": e_score,
            "control": c_score
        },
        "summary": {
            "node_count": len(node_cache),
            "edge_count": len(transition_results),
            "path_count": len(workflow_results)
        },
        "details": {
            "static_analysis": static_results,
            "transition_analysis": transition_results,
            "workflow_analysis": workflow_results
        }
    }
    
    output_filename = f"full_analysis_{run_id}.json"
    output_path = os.path.join(project_root, output_filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*20} Full Analysis Complete! {'='*20}")
    print(f" FINAL SCORE: {total_score} / 100")
    print(f"  - Learnability: {l_score}")
    print(f"  - Efficiency:   {e_score}")
    print(f"  - Control:      {c_score}")

    print(f"\n[Detailed Issue Report - Failed Checks]")
    
    # Static Analysis Failures (Grouping by items and checks)
    for sr in static_results:
        node_id = sr["node_id"][:8]
        for cat in ["learnability", "control"]:
            cat_data = sr["result"].get(cat, {})
            items = cat_data.get("items", [])
            
            # Collect all failed checks for this category
            failed_msgs = []
            for item in items:
                for check in item.get("checks", []):
                    if check.get("status") == "FAIL":
                        failed_msgs.append(check.get("message", "N/A"))
            
            if failed_msgs:
                print(f"  ![Node {node_id}] {cat.capitalize()} Issue:")
                for msg in failed_msgs:
                    print(f"    - {msg}")

    # Transition Analysis Failures
    for tr in transition_results:
        edge_id = tr["edge_id"][:8]
        for cat in ["efficiency", "control"]:
            failed = tr["result"][cat].get("failed", [])
            if failed:
                print(f"  ![Edge {edge_id}] {cat.capitalize()} Issue ({tr['action']}):")
                for f in failed:
                    msg = f["message"] if isinstance(f, dict) else f
                    print(f"    - {msg}")

    # Workflow Analysis Failures
    for wr in workflow_results:
        path_idx = wr["path_index"]
        failed = wr["result"]["efficiency"].get("failed", [])
        if failed:
            print(f"  ![Path {path_idx}] Efficiency Issue:")
            for f in failed:
                msg = f["message"] if isinstance(f, dict) else f
                print(f"    - {msg}")

    print(f"\n[Positive Feedback - Passed Checks]")
    # Static Analysis Successes
    for sr in static_results:
        node_id = sr["node_id"][:8]
        for cat in ["learnability", "control"]:
            passed = sr["result"][cat].get("passed", [])
            if passed:
                print(f"  v[Node {node_id}] {cat.capitalize()} Pass:")
                for p in passed:
                    msg = p["check"]["message"] if isinstance(p["check"], dict) else p["check"]
                    print(f"    - {msg}")

    # Transition Analysis Successes
    for tr in transition_results:
        edge_id = tr["edge_id"][:8]
        for cat in ["efficiency", "control"]:
            passed = tr["result"][cat].get("passed", [])
            if passed:
                print(f"  v[Edge {edge_id}] {cat.capitalize()} Pass ({tr['action']}):")
                for p in passed:
                    msg = p["message"] if isinstance(p, dict) else p
                    print(f"    - {msg}")

    # Workflow Analysis Successes
    for wr in workflow_results:
        path_idx = wr["path_index"]
        passed = wr["result"]["efficiency"].get("passed", [])
        if passed:
            print(f"  v[Path {path_idx}] Efficiency Pass:")
            for p in passed:
                msg = p["message"] if isinstance(p, dict) else p
                print(f"    - {msg}")

    print(f"\nFull details saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perform full analysis for a Run.")
    parser.add_argument("run_id", help="Run UUID to analyze")
    args = parser.parse_args()
    
    try:
        rid = UUID(args.run_id)
        run_full_analysis(rid)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

