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

def main():
    """
    메인 실행 함수. 
    커맨드 라인 인자로 node_id를 받아 다음 단계를 수행합니다:
    1. NodeAnalyzer를 통해 노드 데이터(DOM, CSS, A11y) 로드
    2. ElementExtractor를 통해 DOM에서 인터랙티브 요소 추출
    3. 추출된 요소를 elements.json 파일로 저장
    4. At First Glance(Checklist) 평가 실행 및 결과 출력
    """
    # CLI 인자 파싱
    parser = argparse.ArgumentParser(description="노드 ID로 데이터 분석")
    parser.add_argument("node_id", help="분석할 노드의 UUID")
    args = parser.parse_args()

    try:
        # 1. 분석기 인스턴스 생성 및 데이터 로드
        # 데이터베이스/스토리지에서 해당 노드의 아티팩트를 가져옵니다.
        analyzer = NodeAnalyzer(args.node_id)
        if analyzer.load_data():
            analyzer.print_summary()
            
            # DOM, CSS, 접근성(A11y) 데이터 가져오기
            dom_content = analyzer.get_dom()
            css_content = analyzer.get_css()
            a11y_content = analyzer.get_a11y()

            # DOM 데이터가 존재하는 경우 요소 추출 진행
            if dom_content:
                print("ElementExtractor를 사용하여 요소 분석을 시작합니다...")
                
                # 2. ElementExtractor 초기화 및 실행
                # DOM과 CSS를 기반으로 버튼, 링크, 입력창 등 인터랙티브 요소를 추출합니다.
                extractor = ElementExtractor(dom_content, css_content)
                extraction_result = extractor.extract()
                
                elements = extraction_result.get("elements", [])
                status_components = extraction_result.get("status_components", {})
                
                print(f"분석 완료: 총 {len(elements)}개의 인터랙티브 요소를 찾았습니다.")
                
                # 3. 결과 JSON 구조화
                # 추출된 요소와 상태 컴포넌트, URL 정보를 포함하는 결과 딕셔너리 생성
                result_data = {
                    "node_id": str(analyzer.node_id),
                    "url": analyzer.node_data.get("url", "Unknown"), # 원본 데이터에서 URL 추출
                    "elements": elements,
                    "status_components": status_components
                }

                # elements.json으로 저장 (프로젝트 루트 경로에 저장)
                # 이 파일은 후속 평가 단계에서 입력으로 사용될 수 있습니다.
                output_path = os.path.join(project_root, "elements.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
                
                print(f"결과가 저장되었습니다: {output_path}")

                # 4. Evaluators 실행 (At First Glance Checklist)
                # 추출된 데이터를 바탕으로 접근성 및 명확성 평가를 수행합니다.
                print("\n[Evaluator] At First Glance Checklist 실행 중...")
                
                # 데이터와 JSON 경로를 함께 전달하여 평가 실행
                evaluation_result = check_accessibility(data=result_data, json_path=output_path)
                
                if evaluation_result:
                    # 평가 요약 결과 출력
                    print(f"평가 완료. 요약 - 통과: {evaluation_result['summary']['passed_count']}, 실패: {evaluation_result['summary']['failed_count']}")
                else:
                    print("평가 실행 실패")

    except Exception as e:
        print(f"예상치 못한 오류: {e}")

if __name__ == "__main__":
    main()
