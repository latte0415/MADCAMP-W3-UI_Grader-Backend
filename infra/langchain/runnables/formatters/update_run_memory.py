"""
update-run-memory chain용 입력 포맷터
"""

from typing import Dict, Any, Optional
from infra.langchain.prompts import get_human_input
from . import register_input_formatter


def format_update_run_memory_input(
    run_memory: Dict[str, Any],
    auxiliary_data: Optional[Dict[str, Any]] = None
) -> str:
    """
    update-run-memory chain용 입력 포맷팅
    
    Args:
        run_memory: run_memory의 content 딕셔너리
        auxiliary_data: 보조 자료 딕셔너리 (페이지 정보 포함)
    
    Returns:
        포맷팅된 human input 문자열
    """
    human_template = get_human_input("update-run-memory")
    
    # run_memory를 JSON 문자열로 변환
    import json
    run_memory_str = json.dumps(run_memory, ensure_ascii=False, indent=2)
    
    # 페이지 정보 추가 (일반 사용자가 인지할 수 있는 정보만)
    page_info_parts = []
    if auxiliary_data:
        url = auxiliary_data.get("url")
        if url:
            page_info_parts.append(f"페이지 URL: {url}")
        
        page_title = auxiliary_data.get("page_title")
        if page_title:
            page_info_parts.append(f"페이지 제목: {page_title}")
        
        # 제목들
        headings = auxiliary_data.get("headings", [])
        if headings:
            headings_text = "\n".join([f"  - {h}" for h in headings])
            page_info_parts.append(f"페이지 제목들:\n{headings_text}")
        
        # 문단 텍스트 (처음 5개만)
        paragraphs = auxiliary_data.get("paragraphs", [])
        if paragraphs:
            paragraphs_text = "\n".join([f"  - {p[:150]}..." if len(p) > 150 else f"  - {p}" for p in paragraphs[:5]])
            page_info_parts.append(f"주요 문단:\n{paragraphs_text}")
        
        # 버튼들
        buttons = auxiliary_data.get("buttons", [])
        if buttons:
            buttons_text = ", ".join(buttons[:10])
            page_info_parts.append(f"버튼들: {buttons_text}")
        
        # 링크들 (처음 10개만)
        links = auxiliary_data.get("links", [])
        if links:
            links_text = "\n".join([f"  - {link}" for link in links[:10]])
            page_info_parts.append(f"링크들:\n{links_text}")
        
        # 입력 필드 라벨들
        input_labels = auxiliary_data.get("input_labels", [])
        if input_labels:
            labels_text = ", ".join(input_labels[:10])
            page_info_parts.append(f"입력 필드: {labels_text}")
        
        # 주요 텍스트 콘텐츠 (요약)
        visible_text = auxiliary_data.get("visible_text", "")
        if visible_text:
            page_info_parts.append(f"페이지 주요 텍스트:\n{visible_text}")
    
    page_info_str = "\n".join(page_info_parts) if page_info_parts else "페이지 정보 없음"
    
    # 템플릿에 run_memory와 페이지 정보 추가
    formatted_input = f"{human_template}\n\n현재 run_memory:\n{run_memory_str}\n\n페이지 정보:\n{page_info_str}"
    
    return formatted_input


def _format_update_run_memory(**kwargs) -> str:
    """
    update-run-memory용 내부 포맷터
    
    Args:
        **kwargs: run_memory, auxiliary_data 등
    
    Returns:
        포맷팅된 입력 문자열
    """
    run_memory = kwargs.get("run_memory", {})
    auxiliary_data = kwargs.get("auxiliary_data", {})
    return format_update_run_memory_input(run_memory, auxiliary_data)


# update-run-memory 포맷터 등록
register_input_formatter("update-run-memory", _format_update_run_memory)
