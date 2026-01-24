import sys
import os
import argparse

# 다른 패키지(infra, utils 등)에서 모듈을 임포트할 수 있도록 프로젝트 루트 경로를 sys.path에 추가합니다.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from services.node import NodeAnalyzer
except ImportError:
    from node import NodeAnalyzer

def main():
    """
    메인 실행 함수. 
    커맨드 라인 인자로 node_id를 받아 분석을 수행합니다.
    """
    parser = argparse.ArgumentParser(description="노드 ID로 데이터 분석")
    parser.add_argument("node_id", help="분석할 노드의 UUID")
    args = parser.parse_args()

    try:
        # 분석기 인스턴스 생성 및 데이터 로드
        analyzer = NodeAnalyzer(args.node_id)
        if analyzer.load_data():
            analyzer.print_summary()
            
            # DOM, CSS, A11y 데이터 가져오기
            dom_content = analyzer.get_dom()
            css_content = analyzer.get_css()
            a11y_content = analyzer.get_a11y()

            # 데이터 활용 예시 (필요시 주석 해제하여 사용)
            # if dom_content:
            #     print(f"DOM Content Preview: {dom_content[:100]}...")

            if dom_content:
                print("ElementExtractor를 사용하여 요소 분석을 시작합니다...")
                from services.element_extractor import ElementExtractor
                import json

                extractor = ElementExtractor(dom_content, css_content)
                elements = extractor.extract()
                
                print(f"분석 완료: 총 {len(elements)}개의 인터랙티브 요소를 찾았습니다.")
                
                # 결과 JSON 구조화
                result_data = {
                    "node_id": str(analyzer.node_id),
                    "url": analyzer.node_data.get("url", "Unknown"), # node_data에서 URL 가져오기 시도
                    "elements": elements
                }

                # elements.json으로 저장 (프로젝트 루트에 저장)
                # Analyze.py는 services 폴더에 있으므로 프로젝트 루트는 ..
                output_path = os.path.join(project_root, "elements.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
                
                print(f"결과가 저장되었습니다: {output_path}")

                # === 2. Evaluators 실행 ===
                print("\n[Evaluator] Clarity & Affordance Checklist 실행 중...")
                from evaluators.clarity_affordance.clarity_affordance import check_accessibility
                
                # 데이터와 함께 평가 실행
                evaluation_result = check_accessibility(data=result_data, json_path=output_path)
                
                if evaluation_result:
                    print(f"평가 완료. 요약 - 통과: {evaluation_result['summary']['passed_count']}, 실패: {evaluation_result['summary']['failed_count']}")
                else:
                    print("평가 실행 실패")

                print("\n[Evaluator] Visibility of System Status Checklist 실행 중...")
                from evaluators.Visibility_of_system_status.visibility_of_system_status import check_visibility_of_system_status
                
                # 데이터와 함께 평가 실행
                # 경로는 elements.json과 동일한 위치에 저장되도록 설정
                visibility_result = check_visibility_of_system_status(data=result_data, json_path=output_path)

                if visibility_result:
                    summary = visibility_result['summary']
                    print(f"평가 완료. 요약 - Title Found: {summary['title_found']}, Progress Found: {summary['progress_indicators_found']}, Breadcrumbs: {summary['breadcrumbs_found']}")
                else:
                    print("Visibility 평가 실행 실패")


    except Exception as e:
        print(f"예상치 못한 오류: {e}")

if __name__ == "__main__":
    main()
