"""
웹 검색 도구 설정

Infrastructure 레이어: 외부 검색 도구(Tavily 등) 초기화
"""

import os
from typing import Any
from langchain_community.tools.tavily_search import TavilySearchResults
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


def get_web_search_tools() -> list[Any]:
    """
    웹 검색 도구 목록을 반환합니다.
    
    Returns:
        웹 검색 도구 리스트
    """
    tools = []
    
    # Tavily 검색 도구 추가
    try:
        tavily_tool = TavilySearchResults(
            max_results=3,  # 최대 검색 결과 수
            api_key=TAVILY_API_KEY,  # API 키 (없어도 작동할 수 있음)
        )
        tools.append(tavily_tool)
    except Exception as e:
        # Tavily 초기화 실패 시 경고만 출력하고 계속 진행
        print(f"Warning: Tavily tool initialization failed: {e}")
    
    return tools
