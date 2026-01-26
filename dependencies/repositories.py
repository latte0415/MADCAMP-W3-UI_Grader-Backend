"""Repository 인스턴스 관리
모든 Repository를 싱글톤 패턴으로 관리
"""
from repositories import ai_memory_repository
from repositories import edge_repository
from repositories import node_repository


class Repositories:
    """Repository 인스턴스 컨테이너"""

    def __init__(self):
        """ai_memory, edge, node 리포지토리 모듈 참조 저장 (함수 기반)."""
        # Repository는 함수 기반이므로 모듈 자체를 참조
        self.ai_memory = ai_memory_repository
        self.edge = edge_repository
        self.node = node_repository


# 싱글톤 인스턴스
_repositories_instance: Repositories = None


def get_repositories() -> Repositories:
    """
    Repository 인스턴스 반환 (싱글톤)
    
    Returns:
        Repositories 인스턴스
    """
    global _repositories_instance
    if _repositories_instance is None:
        _repositories_instance = Repositories()
    return _repositories_instance
