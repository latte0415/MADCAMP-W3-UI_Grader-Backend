"""OpenAI Moderation API를 사용한 콘텐츠 검사 유틸리티"""
import os
from typing import Dict, Any, Optional, Tuple
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# OpenAI 클라이언트 초기화
_openai_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """OpenAI 클라이언트 싱글톤 인스턴스 반환"""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def check_text_moderation(text: str) -> Tuple[bool, Dict[str, Any]]:
    """
    텍스트를 Moderation API로 검사합니다.
    
    Args:
        text: 검사할 텍스트
    
    Returns:
        (is_safe, moderation_result) 튜플
        - is_safe: True면 안전, False면 정책 위반 가능성
        - moderation_result: Moderation API 응답 딕셔너리
    """
    try:
        client = get_openai_client()
        response = client.moderations.create(input=text)
        
        result = response.results[0]
        is_safe = not result.flagged
        
        moderation_result = {
            "flagged": result.flagged,
            "categories": result.categories.model_dump() if hasattr(result.categories, 'model_dump') else {},
            "category_scores": result.category_scores.model_dump() if hasattr(result.category_scores, 'model_dump') else {},
        }
        
        return is_safe, moderation_result
    except Exception as e:
        # Moderation API 실패 시 안전하다고 가정하고 계속 진행
        print(f"[Moderation] 텍스트 검사 실패 (계속 진행): {e}")
        return True, {"error": str(e)}


def check_image_moderation_via_prompt(prompt_text: str) -> Tuple[bool, Dict[str, Any]]:
    """
    이미지와 관련된 프롬프트 텍스트를 Moderation API로 검사합니다.
    
    이미지 자체는 직접 검사할 수 없으므로, 이미지 설명이나 프롬프트를 검사합니다.
    
    Args:
        prompt_text: 이미지와 함께 전송될 프롬프트 텍스트
    
    Returns:
        (is_safe, moderation_result) 튜플
    """
    return check_text_moderation(prompt_text)


def check_update_run_memory_prompt(
    url: Optional[str] = None,
    run_memory_content: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    update_run_memory 프롬프트를 검사합니다.
    
    Args:
        url: 페이지 URL
        run_memory_content: 현재 run_memory 내용
    
    Returns:
        (is_safe, moderation_result) 튜플
    """
    # 프롬프트 구성 요소들을 검사
    check_texts = []
    
    if url:
        check_texts.append(f"URL: {url}")
    
    if run_memory_content:
        # run_memory의 주요 내용을 텍스트로 변환
        memory_text = " ".join([f"{k}: {v}" for k, v in list(run_memory_content.items())[:10]])
        check_texts.append(f"Memory: {memory_text}")
    
    combined_text = " ".join(check_texts) if check_texts else "update run memory"
    
    return check_text_moderation(combined_text)
