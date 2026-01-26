"""
LLM 결과 추출 유틸리티

Agent 실행 결과에서 특정 툴의 반환값을 추출하는 함수들
"""

from typing import Dict, Any, List, Optional
import json


def format_auxiliary_data_for_input(auxiliary_data: Optional[Dict[str, Any]]) -> str:
    """
    auxiliary_data를 human_input에 추가할 수 있는 텍스트 형식으로 변환합니다.
    
    Args:
        auxiliary_data: 보조 자료 딕셔너리
    
    Returns:
        human_input에 추가할 텍스트 문자열
    """
    if not auxiliary_data:
        return ""
    
    auxiliary_text = "\n\n입력 액션 리스트:\n"
    for key, value in auxiliary_data.items():
        if key == "input_actions":
            # JSON 문자열인 경우 파싱하여 보기 좋게 표시
            try:
                actions_list = json.loads(value)
                auxiliary_text += f"\n{json.dumps(actions_list, ensure_ascii=False, indent=2)}\n"
            except json.JSONDecodeError:
                auxiliary_text += f"{value}\n"
        else:
            auxiliary_text += f"- {key}: {value}\n"
    
    return auxiliary_text


def extract_final_response_result(result: Any) -> List[Dict[str, Any]]:
    """
    LLM 결과에서 final_response 툴의 반환값을 추출합니다.
    
    Args:
        result: AgentExecutor 실행 결과
    
    Returns:
        처리 가능한 액션 리스트 (파싱 실패 시 빈 리스트)
    """
    try:
        # result가 딕셔너리이고 intermediate_steps가 있는 경우
        if isinstance(result, dict) and "intermediate_steps" in result:
            for action, observation in result["intermediate_steps"]:
                # final_response 툴 호출 확인
                if hasattr(action, "tool") and action.tool == "final_response":
                    # observation이 dict이고 "actions" 키가 있으면 사용
                    if isinstance(observation, dict) and "actions" in observation:
                        return observation["actions"]
                    # observation이 문자열인 경우 JSON 파싱 시도
                    elif isinstance(observation, str):
                        try:
                            parsed = json.loads(observation)
                            if isinstance(parsed, dict) and "actions" in parsed:
                                return parsed["actions"]
                        except json.JSONDecodeError:
                            pass
        
        # output이 있는 경우 (문자열)
        if isinstance(result, dict) and "output" in result:
            output = result["output"]
            if isinstance(output, str):
                # JSON 파싱 시도
                try:
                    parsed = json.loads(output)
                    if isinstance(parsed, dict) and "actions" in parsed:
                        return parsed["actions"]
                except json.JSONDecodeError:
                    pass
        
        # 파싱 실패 시 빈 리스트 반환
        print(f"[extract_final_response_result] final_response 툴 결과를 찾을 수 없음. result: {result}")
        return []
    except Exception as e:
        print(f"[extract_final_response_result] 에러: {e}")
        return []
