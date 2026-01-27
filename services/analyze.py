## 화면을 보는 순간에 대한 analyze
## 한 개의 노드가 주어진다고 가정

# 필요한 표준 라이브러리 임포트
import sys
import os
import argparse
import json 

# 프로젝트 루트 경로 설정 (다른 모듈 임포트를 위해 필요)
# 현재 파일(analyze.py)의 상위 상위 디렉토리를 프로젝트 루트로 간주합니다.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# 서비스 및 평가 모듈 임포트
# ImportError 처리: 실행 위치에 따라 경로 인식이 다를 수 있어 폴백 처리
try:
    from services.node import NodeAnalyzer
    from services.element_extractor import ElementExtractor
    from evaluators.at_first_glance.at_first_glance import check_accessibility
except ImportError:
    from node import NodeAnalyzer
    from services.element_extractor import ElementExtractor
    from evaluators.at_first_glance.at_first_glance import check_accessibility

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

def main():
    """
    메인 실행 함수. 
    커맨드 라인 인자로 node_id를 받아 analyze_single_node를 호출합니다.
    """
    parser = argparse.ArgumentParser(description="노드 ID로 데이터 분석")
    parser.add_argument("node_id", help="분석할 노드의 UUID")
    args = parser.parse_args()

    evaluation_result = analyze_single_node(args.node_id)
    if evaluation_result:
        # 새로운 구조(items 내 checks)에 맞춰 통과/실패 합산
        def count_stats(category):
            p, f = 0, 0
            for item in evaluation_result.get(category, {}).get("items", []):
                for check in item.get("checks", []):
                    if check.get("status") == "FAIL": f += 1
                    else: p += 1
            return p, f

        l_p, l_f = count_stats("learnability")
        c_p, c_f = count_stats("control")
        
        passed = l_p + c_p
        failed = l_f + c_f
        print(f"\n[Main] 평가 완료. 요약 - 통과: {passed}, 실패: {failed}")

if __name__ == "__main__":
    main()
