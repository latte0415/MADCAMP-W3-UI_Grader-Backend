import sys
import os
from uuid import UUID
from typing import Optional, Dict, Any

# 다른 패키지(infra, utils 등)에서 모듈을 임포트할 수 있도록 프로젝트 루트 경로를 sys.path에 추가합니다.
# 이 파일이 단독으로 실행되지 않더라도, 임포트 시 안전을 위해 추가할 수 있습니다.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from services.node_service import get_node_with_artifacts
except ImportError:
    # 패키지 구조 해석 실패 시 폴백
    from node_service import get_node_with_artifacts

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
