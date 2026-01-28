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
        # 1. 데이터 조회 (생성 시간 순으로 정렬)
        nodes = self.node_repo.get_nodes_by_run_id(run_id)
        edges = self.edge_repo.get_edges_by_run_id(run_id)
        # 생성 시간 순으로 명시적으로 정렬 (이미 repository에서 정렬하지만 안전을 위해 한 번 더)
        nodes = sorted(nodes, key=lambda x: x.get('created_at', ''))

        # for node in nodes:
        #     print(node['id'])
        
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
        가장 먼저 생성된 루트 노드에서 시작하여 도달 가능한 모든 가능한 경로를 BFS로 탐색합니다.
        리프 노드에 도달하거나, 사이클이 발생하는 지점까지의 모든 시나리오를 추출합니다.
        """
        from collections import deque
        
        graph_data = self.get_run_graph(run_id)
        nodes = graph_data["nodes"]
        matrix = graph_data["matrix"]
        num_nodes = len(nodes)
        
        if num_nodes == 0:
            return []

        # 1. 루트 노드 식별 (생성 시간 기준 가장 빠른 노드 - 이미 정렬됨)
        root_idx = 0
            
        print(f"[Graph] Root Node identified: {nodes[root_idx].get('id')} at index {root_idx}")

        # 2. 리프 노드(Terminal Nodes) 식별
        leaf_indices = [i for i in range(num_nodes) if all(len(matrix[i][j]) == 0 for j in range(num_nodes))]
        
        all_paths = []
        
        # 3. BFS 탐색을 위한 큐 초기화
        # queue item: (current_node_index, path_nodes_already_visited, path_edges_list)
        queue = deque([(root_idx, [], [])])

        while queue:
            curr_idx, curr_path_nodes, curr_path_edges = queue.popleft()
            curr_node = nodes[curr_idx]
            
            # 경로 업데이트
            new_path_nodes = curr_path_nodes + [curr_node]
            
            # 다음 노드들 탐색
            neighbors_found = False
            for next_idx in range(num_nodes):
                edges_list = matrix[curr_idx][next_idx]
                for edge in edges_list:
                    neighbors_found = True
                    # 사이클 감지: 다음 노드가 이미 현재 경로에 존재하면 중단하고 해당 지점까지의 경로를 저장
                    if any(str(n['id']) == str(nodes[next_idx]['id']) for n in new_path_nodes):
                        all_paths.append({
                            "nodes": new_path_nodes + [nodes[next_idx]],
                            "edges": curr_path_edges + [edge],
                            "is_cycle": True
                        })
                    else:
                        # 각 엣지별로 새로운 경로 탐색을 큐에 추가
                        queue.append((next_idx, new_path_nodes, curr_path_edges + [edge]))

            # 리프 노드(더 이상 나가는 엣지가 없는 경우) 도달 시 결과 저장
            if not neighbors_found:
                all_paths.append({
                    "nodes": new_path_nodes,
                    "edges": curr_path_edges,
                    "is_cycle": False
                })

        print(f"[Graph] Total {len(all_paths)} paths detected (including cycles).")
        for i, path_data in enumerate(all_paths, 1):
            nodes = path_data["nodes"]
            suffix = " (Cycle)" if path_data.get("is_cycle") else ""
            display_str = " -> ".join([str(node['id'])[:8] for node in nodes])
            print(f"  Route {i}: {display_str}{suffix}")

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
                display_str = " -> ".join([str(node['id'])[:8] for node in nodes])
                print(f"    {display_str}")
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Usage: python services/graph_service.py <RUN_ID>")
