"""Service 인스턴스 관리
Repository를 주입하여 Service 인스턴스 생성
"""
from dependencies.repositories import get_repositories
from services.ai_service import AiService
from services.edge_service import EdgeService
from services.node_service import NodeService
from services.pending_action_service import PendingActionService


class Services:
    """Service 인스턴스 컨테이너"""
    
    def __init__(self, repositories=None):
        if repositories is None:
            repositories = get_repositories()
        
        self.ai = AiService()
        self.node = NodeService(repositories.node)
        self.edge = EdgeService(repositories.edge, repositories.node, self.node)
        self.pending_action = PendingActionService(repositories.ai_memory)


# 싱글톤 인스턴스
_services_instance: Services = None


def get_services(repositories=None) -> Services:
    """
    Service 인스턴스 반환 (싱글톤)
    
    Args:
        repositories: Repository 인스턴스 (기본값: None, 싱글톤 사용)
    
    Returns:
        Services 인스턴스
    """
    global _services_instance
    if _services_instance is None:
        _services_instance = Services(repositories)
    return _services_instance
