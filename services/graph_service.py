"""Graph Service
run_id를 기반으로 노드 목록, 엣지 목록 및 인접 행렬(Relationship Matrix)을 생성합니다.
"""
import sys
import os

# Import path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from typing import Dict, List, Any
from uuid import UUID
import numpy as np

try:
    from repositories import node_repository
    from repositories import edge_repository
except ImportError:
    import node_repository
    import edge_repository

from utils.logger import get_logger

logger = get_logger(__name__)

class GraphService:
    def __init__(self, node_repo=None, edge_repo=None):
        self.node_repo = node_repo or node_repository
        self.edge_repo = edge_repo or edge_repository

    def get_run_graph(self, run_id: UUID) -> Dict[str, Any]:
        """
        특정 run_id에 대한 전체 그래프 데이터 반환
        """
        # 1. 데이터 조회
        nodes = self.node_repo.get_nodes_by_run_id(run_id)
        edges = self.edge_repo.get_edges_by_run_id(run_id)
        
        # 2. 노드 ID -> 인덱스 맵핑 (행렬 생성을 위해)
        node_id_to_idx = {str(node['id']): i for i, node in enumerate(nodes)}
        num_nodes = len(nodes)
        
        # 3. 관계 행렬 (Adjacency Matrix) 생성
        # matrix[u][v] 에 해당 구간의 엣지 객체 리스트를 저장
        matrix = [[[] for _ in range(num_nodes)] for _ in range(num_nodes)]
        
        for edge in edges:
            from_id = str(edge.get('from_node_id'))
            to_id = str(edge.get('to_node_id'))
            
            if from_id in node_id_to_idx and to_id in node_id_to_idx:
                u = node_id_to_idx[from_id]
                v = node_id_to_idx[to_id]
                matrix[u][v].append(edge)
        
        return {
            "run_id": str(run_id),
            "nodes": nodes,
            "edges": edges,
            "matrix": matrix,
            "node_count": num_nodes,
            "edge_count": len(edges)
        }

    def find_all_paths(self, run_id: UUID) -> List[Dict[str, Any]]:
        """
        시작 노드에서 리프 노드까지의 모든 경로(노드 리스트 & 엣지 리스트)를 찾습니다.
        """
        graph_data = self.get_run_graph(run_id)
        nodes = graph_data["nodes"]
        matrix = graph_data["matrix"]
        num_nodes = len(nodes)
        
        if num_nodes == 0:
            return []

        # 1. 시작 노드 찾기
        start_indices = [i for i, n in enumerate(nodes) if n.get('interaction_depth') == 0]
        if not start_indices:
            start_indices = [0]

        # 2. 리프 노드(Terminal Nodes) 식별
        # 행렬의 해당 행이 비어있으면(모든 열의 리스트가 빈 리스트면) 나가는 엣지가 없음
        leaf_indices = [i for i in range(num_nodes) if all(len(matrix[i][j]) == 0 for j in range(num_nodes))]
        
        all_paths = []

        def dfs(current_idx: int, path_nodes: List[Dict], path_edges: List[Dict], visited_node_idxs: set):
            # 사이클 방지 (노드 인덱스 기준)
            if current_idx in visited_node_idxs:
                return
            
            # 현재 노드 추가
            new_path_nodes = path_nodes + [nodes[current_idx]]
            
            # 리프 노드에 도달했으면 경로 저장
            if current_idx in leaf_indices:
                all_paths.append({
                    "nodes": new_path_nodes,
                    "edges": path_edges
                })
                return
            
            # 방문 표시
            new_visited = visited_node_idxs | {current_idx}
            
            # 다음 노드들 탐색
            for next_idx in range(num_nodes):
                edges_list = matrix[current_idx][next_idx]
                for edge in edges_list:
                    # 각 엣지별로 별도의 경로 생성 가능 (만약 동일 노드간 여러 액션이 있다면)
                    dfs(next_idx, new_path_nodes, path_edges + [edge], new_visited)

        for start_idx in start_indices:
            dfs(start_idx, [], [], set())

        return all_paths

    def get_full_analysis(self, run_id: UUID) -> Dict[str, Any]:
        """
        그래프 데이터(노드, 엣지, 인접 행렬)와 DFS 경로 탐색 결과를 한꺼번에 반환합니다.
        """
        graph_data = self.get_run_graph(run_id)
        paths = self.find_all_paths(run_id)
        
        graph_data["paths"] = paths
        return graph_data

def get_run_graph_analysis(run_id: UUID) -> Dict[str, Any]:
    """
    외부에서 간편하게 호출할 수 있는 통합 분석 함수입니다.
    """
    service = GraphService()
    return service.get_full_analysis(run_id)

if __name__ == "__main__":
    # 간단한 테스트용 (실제 run_id 필요)
    import sys
    if len(sys.argv) > 1:
        run_id_str = sys.argv[1]
        try:
            rid = UUID(run_id_str)
            service = GraphService()
            
            # 1. 기본 그래프 정보
            graph = service.get_run_graph(rid)
            print(f"--- Graph Info for Run: {rid} ---")
            print(f"Nodes: {graph['node_count']}")
            print(f"Edges: {graph['edge_count']}")
            print("\nRelationship Matrix (Stored Edge counts):")
            for row in graph['matrix']:
                counts = [len(cell) for cell in row]
                print(f"  {counts}")
            
            # 2. 경로 탐색 테스트
            print("\n--- Finding All Paths (DFS) ---")
            paths = service.find_all_paths(rid)
            print(f"Detected {len(paths)} paths from start to leaf:")
            
            for i, path_data in enumerate(paths, 1):
                nodes = path_data["nodes"]
                edges = path_data["edges"]
                
                print(f"  Path {i}:")
                # 노드와 엣지를 번갈아가며 출력
                display_str = str(nodes[0]['id'])[:8]
                for j in range(len(edges)):
                    edge_label = edges[j].get('intent_label') or edges[j].get('action_type')
                    display_str += f" --({edge_label})--> {str(nodes[j+1]['id'])[:8]}"
                print(f"    {display_str}")
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Usage: python services/graph_service.py <RUN_ID>")
