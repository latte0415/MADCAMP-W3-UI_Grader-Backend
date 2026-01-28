"""Analysis Service
노드, 엣지, 워크플로우 분석을 수행하는 서비스입니다.
"""
import sys
import os
import json
import argparse
from uuid import UUID
from typing import Optional, Dict, Any
from datetime import datetime

# 프로젝트 루트 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# 서비스 및 평가 모듈 임포트
try:
    from services.node_service import get_node_with_artifacts
    from services.edge_service import get_edge_by_id
    from utils.element_extractor import ElementExtractor
    from services.graph_service import get_run_graph_analysis
    from evaluators.at_first_glance.at_first_glance import check_accessibility
    from evaluators.after_actions.after_actions import evaluate_after_action
    from evaluators.doing_actions.doing_actions import evaluate_doing_actions
    from utils.logger import get_logger
    from playwright.sync_api import sync_playwright
except ImportError:
    # Fallback imports
    from node_service import get_node_with_artifacts
    from edge_service import get_edge_by_id
    from utils.element_extractor import ElementExtractor
    from graph_service import get_run_graph_analysis
    from evaluators.at_first_glance.at_first_glance import check_accessibility
    from evaluators.after_actions.after_actions import evaluate_after_action
    from evaluators.doing_actions.doing_actions import evaluate_doing_actions
    from utils.logger import get_logger
    from playwright.sync_api import sync_playwright

logger = get_logger(__name__)


class NodeAnalyzer:
    """
    노드 분석기 클래스
    
    특정 노드 ID에 해당하는 아티팩트(DOM, CSS, A11y 스냅샷)를 조회하고 
    분석하기 위한 기능을 제공합니다.
    """
    def __init__(self, node_id: str | UUID):
        """
        초기화 메서드
        
        Args:
            node_id (str | UUID): 분석할 노드의 UUID
        """
        if isinstance(node_id, str):
            try:
                self.node_id = UUID(node_id)
            except ValueError:
                raise ValueError(f"유효하지 않은 UUID 문자열입니다: {node_id}")
        else:
            self.node_id = node_id
            
        self.node_data: Optional[Dict[str, Any]] = None
        self.artifacts: Dict[str, Any] = {}
        
    def load_data(self) -> bool:
        """
        데이터베이스 및 스토리지에서 노드 데이터와 아티팩트를 로드합니다.
        
        Returns:
            bool: 데이터 로드 성공 여부 (노드가 존재하면 True, 없으면 False)
        """
        print(f"노드 데이터 로딩 중: {self.node_id}...")
        try:
            # node_service를 통해 아티팩트가 포함된 노드 정보를 가져옵니다.
            self.node_data = get_node_with_artifacts(self.node_id)
            
            if not self.node_data:
                print(f"데이터베이스에서 노드 {self.node_id}를 찾을 수 없습니다.")
                return False
            
            # 아티팩트 딕셔너리를 별도로 저장해 접근을 쉽게 합니다.
            self.artifacts = self.node_data.get("artifacts", {})
            return True
        except Exception as e:
            print(f"노드 데이터 로드 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_dom(self) -> Optional[str]:
        """
        DOM 스냅샷 HTML 내용을 반환합니다.
        
        Returns:
            str | None: HTML 문자열 또는 데이터가 없는 경우 None
        """
        return self.artifacts.get("dom_snapshot_html")

    def get_css(self) -> Optional[str]:
        """
        CSS 스냅샷 내용을 반환합니다.
        
        Returns:
            str | None: CSS 문자열 또는 데이터가 없는 경우 None
        """
        return self.artifacts.get("css_snapshot")

    def get_a11y(self) -> Optional[Dict]:
        """
        접근성(Accessibility) 스냅샷 JSON 데이터를 반환합니다.
        
        Returns:
            dict | None: 접근성 트리 데이터 또는 오류 정보, 데이터가 없는 경우 None
        """
        return self.artifacts.get("a11y_snapshot")

    def print_summary(self):
        """
        로드된 아티팩트 데이터의 요약 정보를 출력합니다.
        데이터가 로드되지 않은 경우 경고 메시지를 출력합니다.
        """
        if not self.node_data:
            print("데이터가 로드되지 않았습니다. load_data()를 먼저 호출해주세요.")
            return

        print("\n=== 분석 결과 ===")
        print(f"노드 {self.node_id} 데이터 로드 성공")
        
        # DOM 정보 출력
        dom = self.get_dom()
        if dom:
            print(f"- DOM 길이: {len(dom)} characters")
        else:
            print("- DOM: 찾을 수 없음")
            
        # CSS 정보 출력
        css = self.get_css()
        if css:
            print(f"- CSS 길이: {len(css)} characters")
        else:
            print("- CSS: 찾을 수 없음")

        # 접근성 정보 출력
        a11y = self.get_a11y()
        if a11y:
            if isinstance(a11y, dict):
                # 접근성 스냅샷 생성 중 오류가 발생했는지 확인
                if "error" in a11y:
                    print(f"- A11y 스냅샷 오류: {a11y['error']}")
                else:
                    print(f"- A11y 스냅샷 최상위 키: {list(a11y.keys())}")
            else:
                 print(f"- A11y 스냅샷 타입: {type(a11y)}")
        else:
            print("- A11y: 찾을 수 없음")


class AnalysisService:
    """분석 서비스 클래스"""
    
    @staticmethod
    def analyze_single_node(node_id: str, node_data: dict = None):
        """
        단일 노드 분석 수행.
        node_data가 제공되면 NodeAnalyzer 및 ElementExtractor 로딩을 건너뜁니다.
        """
        try:
            if node_data is not None:
                print(f"이미 처리된 데이터를 사용합니다: Node {node_id}")
                result_data = node_data
            else:
                # 1. 분석기 인스턴스 생성 및 데이터 로드
                analyzer = NodeAnalyzer(node_id)
                if not analyzer.load_data():
                    print(f"데이터 로드 실패: {node_id}")
                    return None
                
                analyzer.print_summary()
                
                dom_content = analyzer.get_dom()
                css_content = analyzer.get_css()

                if not dom_content:
                    print("DOM 데이터가 없습니다.")
                    return None

                print("ElementExtractor를 사용하여 요소 분석을 시작합니다...")
                extractor = ElementExtractor(dom_content, css_content)
                extraction_result = extractor.extract()
                
                elements = extraction_result.get("elements", [])
                status_components = extraction_result.get("status_components", {})

                print(f"분석 완료: 총 {len(elements)}개의 인터랙티브 요소를 찾았습니다.")
                
                result_data = {
                    "node_id": str(node_id),
                    "url": analyzer.node_data.get("url", "Unknown"),
                    "elements": elements,
                    "status_components": status_components
                }

                # elements.json으로 저장 (하위 호환 및 디버깅용)
                output_path = os.path.join(project_root, "elements.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
                print(f"결과가 저장되었습니다: {output_path}")

            # 4. Evaluators 실행 (At First Glance Checklist)
            print("\n[Evaluator] At First Glance Checklist 실행 중...")
            evaluation_result = check_accessibility(data=result_data)
            
            if evaluation_result:
                # check_accessibility 결과 구조에 맞춰 summary 출력 (필요시 수정)
                # 여기서는 API 응답 또는 콘솔 출력 용도로 결과 반환
                return evaluation_result
            else:
                print("평가 실행 실패")
                return None

        except Exception as e:
            print(f"분석 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
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

    @staticmethod
    def analyze_transition(edge_id, edge_data=None, prev_node_data=None, next_node_data=None):
        """
        이동(액션 직후 피드백) 분석 수행.
        데이터가 제공되면 로딩 및 요소 추출 과정을 건너뜁니다.
        """
        try:
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

    @staticmethod
    def run_full_analysis(run_id: UUID):
        """
        한 개의 Run에 대해 정적 분석(Node), 전이 분석(Edge), 워크플로우 분석(DFS Paths)을 모두 수행합니다.
        """
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
        
        for node_id, node_data in node_cache.items():
            try:
                eval_res = AnalysisService.analyze_single_node(node_id=node_id, node_data=node_data)
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
        
        for edge in edges_raw:
            edge_id = str(edge.get('id'))
            from_id = str(edge.get('from_node_id'))
            to_id = str(edge.get('to_node_id'))
            
            prev_data = node_cache.get(from_id, {})
            next_data = node_cache.get(to_id, {})
            
            try:
                eval_res = AnalysisService.analyze_transition(edge_id=edge_id, edge_data=edge, prev_node_data=prev_data, next_node_data=next_data)
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
                eval_res = AnalysisService.analyze_workflow(edge_ids=None, chain_data=chain_data)
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
        return final_output


# Convenience functions for backward compatibility
def analyze_single_node(node_id: str, node_data: dict = None):
    """단일 노드 분석 (하위 호환용)"""
    return AnalysisService.analyze_single_node(node_id, node_data)


def analyze_workflow(edge_ids, chain_data=None):
    """워크플로우 분석 (하위 호환용)"""
    return AnalysisService.analyze_workflow(edge_ids, chain_data)


def analyze_transition(edge_id, edge_data=None, prev_node_data=None, next_node_data=None):
    """전이 분석 (하위 호환용)"""
    return AnalysisService.analyze_transition(edge_id, edge_data, prev_node_data, next_node_data)


def run_full_analysis(run_id: UUID):
    """전체 분석 실행 (하위 호환용)"""
    return AnalysisService.run_full_analysis(run_id)


# CLI 실행을 위한 main 함수들
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python analysis_service.py analyze <node_id>")
        print("  python analysis_service.py workflow <edge_id1> <edge_id2> ...")
        print("  python analysis_service.py transition <edge_id>")
        print("  python analysis_service.py full <run_id>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "analyze":
        if len(sys.argv) < 3:
            print("Error: node_id required")
            sys.exit(1)
        result = analyze_single_node(sys.argv[2])
        if result:
            def count_stats(category):
                p, f = 0, 0
                for item in result.get(category, {}).get("items", []):
                    for check in item.get("checks", []):
                        if check.get("status") == "FAIL": f += 1
                        else: p += 1
                return p, f

            l_p, l_f = count_stats("learnability")
            c_p, c_f = count_stats("control")
            
            passed = l_p + c_p
            failed = l_f + c_f
            print(f"\n[Main] 평가 완료. 요약 - 통과: {passed}, 실패: {failed}")
    
    elif command == "workflow":
        if len(sys.argv) < 3:
            print("Error: at least one edge_id required")
            sys.exit(1)
        analyze_workflow(sys.argv[2:])
    
    elif command == "transition":
        if len(sys.argv) < 3:
            print("Error: edge_id required")
            sys.exit(1)
        print(f"--- Analyzing Transition for Edge: {sys.argv[2]} ---")
        analyze_transition(sys.argv[2])
    
    elif command == "full":
        if len(sys.argv) < 3:
            print("Error: run_id required")
            sys.exit(1)
        try:
            rid = UUID(sys.argv[2])
            run_full_analysis(rid)
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
