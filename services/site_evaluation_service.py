"""사이트 평가 서비스"""
from typing import Dict, List, Optional
from uuid import UUID
from datetime import datetime

from repositories import site_evaluation_repository
from utils.logger import get_logger

logger = get_logger(__name__)


class SiteEvaluationService:
    """사이트 평가 관련 비즈니스 로직"""
    
    def __init__(self, evaluation_repo=None):
        """
        Args:
            evaluation_repo: SiteEvaluationRepository 모듈 (기본값: site_evaluation_repository)
        """
        self.evaluation_repo = evaluation_repo or site_evaluation_repository
    
    def save_evaluation(self, run_id: UUID, evaluation_data: Dict) -> Dict:
        """
        사이트 평가 결과 저장
        
        Args:
            run_id: 탐색 세션 ID
            evaluation_data: 평가 결과 JSON 데이터 (full_analysis JSON 구조)
        
        Returns:
            저장된 평가 정보 딕셔너리
        
        Raises:
            ValueError: 필수 필드가 없을 때
            EntityCreationError: 저장 실패 시
        """
        # 1. 최상위 평가 정보 추출
        timestamp_str = evaluation_data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now()
        
        total_score = evaluation_data.get("total_score", 0.0)
        category_scores = evaluation_data.get("category_scores", {})
        summary = evaluation_data.get("summary", {})
        details = evaluation_data.get("details", {})
        
        # 2. 사이트 평가 메인 레코드 생성
        site_evaluation_data = {
            "run_id": str(run_id),
            "timestamp": timestamp.isoformat(),
            "total_score": float(total_score),
            "learnability_score": float(category_scores.get("learnability", 0.0)),
            "efficiency_score": float(category_scores.get("efficiency", 0.0)),
            "control_score": float(category_scores.get("control", 0.0)),
            "node_count": int(summary.get("node_count", 0)),
            "edge_count": int(summary.get("edge_count", 0)),
            "path_count": int(summary.get("path_count", 0)),
        }
        
        site_evaluation = self.evaluation_repo.create_site_evaluation(site_evaluation_data)
        site_evaluation_id = UUID(site_evaluation["id"])
        
        # 3. 노드 평가 저장 (static_analysis)
        static_analysis = details.get("static_analysis", [])
        for node_analysis in static_analysis:
            self._save_node_evaluation(site_evaluation_id, node_analysis)
        
        # 4. 엣지 평가 저장 (transition_analysis)
        transition_analysis = details.get("transition_analysis", [])
        for edge_analysis in transition_analysis:
            self._save_edge_evaluation(site_evaluation_id, edge_analysis)
        
        # 5. 워크플로우 평가 저장 (workflow_analysis)
        workflow_analysis = details.get("workflow_analysis", [])
        if workflow_analysis:
            for workflow_item in workflow_analysis:
                self._save_workflow_evaluation(site_evaluation_id, workflow_item)
        
        return site_evaluation
    
    def _save_node_evaluation(self, site_evaluation_id: UUID, node_analysis: Dict) -> Dict:
        """
        노드 평가 저장
        
        Args:
            site_evaluation_id: 사이트 평가 ID
            node_analysis: 노드 분석 데이터
        
        Returns:
            저장된 노드 평가 정보 딕셔너리
        """
        node_id = node_analysis.get("node_id")
        if not node_id:
            logger.warning("node_id가 없는 노드 평가 데이터를 건너뜁니다.")
            return None
        
        url = node_analysis.get("url", "")
        result = node_analysis.get("result", {})
        
        learnability = result.get("learnability", {})
        efficiency = result.get("efficiency", {})
        control = result.get("control", {})
        
        node_evaluation_data = {
            "site_evaluation_id": str(site_evaluation_id),
            "node_id": str(node_id),
            "url": url,
            "learnability_score": float(learnability.get("score", 0.0)),
            "efficiency_score": float(efficiency.get("score", 0.0)),
            "control_score": float(control.get("score", 0.0)),
            "learnability_items": learnability.get("items", []),
            "efficiency_items": efficiency.get("items", []),
            "control_items": control.get("items", []),
        }
        
        return self.evaluation_repo.create_node_evaluation(node_evaluation_data)
    
    def _save_edge_evaluation(self, site_evaluation_id: UUID, edge_analysis: Dict) -> Dict:
        """
        엣지 평가 저장
        
        Args:
            site_evaluation_id: 사이트 평가 ID
            edge_analysis: 엣지 분석 데이터
        
        Returns:
            저장된 엣지 평가 정보 딕셔너리
        """
        edge_id = edge_analysis.get("edge_id")
        if not edge_id:
            logger.warning("edge_id가 없는 엣지 평가 데이터를 건너뜁니다.")
            return None
        
        action = edge_analysis.get("action", "")
        result = edge_analysis.get("result", {})
        
        learnability = result.get("learnability", {})
        efficiency = result.get("efficiency", {})
        control = result.get("control", {})
        
        # 지연 시간 정보 추출
        latency_info = efficiency.get("latency", {})
        latency_duration_ms = latency_info.get("duration_ms")
        latency_status = latency_info.get("status")
        latency_description = latency_info.get("description")
        
        edge_evaluation_data = {
            "site_evaluation_id": str(site_evaluation_id),
            "edge_id": str(edge_id),
            "action": action,
            "learnability_score": float(learnability.get("score", 0.0)),
            "efficiency_score": float(efficiency.get("score", 0.0)),
            "control_score": float(control.get("score", 0.0)),
            "latency_duration_ms": int(latency_duration_ms) if latency_duration_ms is not None else None,
            "latency_status": latency_status,
            "latency_description": latency_description,
            "learnability_passed": learnability.get("passed", []),
            "learnability_failed": learnability.get("failed", []),
            "efficiency_passed": efficiency.get("passed", []),
            "efficiency_failed": efficiency.get("failed", []),
            "control_passed": control.get("passed", []),
            "control_failed": control.get("failed", []),
        }
        
        return self.evaluation_repo.create_edge_evaluation(edge_evaluation_data)
    
    def _save_workflow_evaluation(self, site_evaluation_id: UUID, workflow_item: Dict) -> Dict:
        """
        워크플로우 평가 저장
        
        Args:
            site_evaluation_id: 사이트 평가 ID
            workflow_item: 워크플로우 분석 데이터
        
        Returns:
            저장된 워크플로우 평가 정보 딕셔너리
        """
        workflow_evaluation_data = {
            "site_evaluation_id": str(site_evaluation_id),
            "workflow_data": workflow_item,
        }
        
        return self.evaluation_repo.create_workflow_evaluation(workflow_evaluation_data)
    
    def get_evaluation_by_run_id(self, run_id: UUID, include_details: bool = True) -> Optional[Dict]:
        """
        run_id로 평가 결과 조회
        
        Args:
            run_id: 탐색 세션 ID
            include_details: 상세 정보 포함 여부
        
        Returns:
            평가 결과 딕셔너리 또는 None
        """
        site_evaluation = self.evaluation_repo.get_site_evaluation_by_run_id(run_id)
        if not site_evaluation:
            return None
        
        if not include_details:
            return site_evaluation
        
        # 상세 정보 포함
        site_evaluation_id = UUID(site_evaluation["id"])
        
        # 노드 평가 목록
        node_evaluations = self.evaluation_repo.get_node_evaluations_by_site_evaluation_id(site_evaluation_id)
        
        # 엣지 평가 목록
        edge_evaluations = self.evaluation_repo.get_edge_evaluations_by_site_evaluation_id(site_evaluation_id)
        
        # 워크플로우 평가 목록
        workflow_evaluations = self.evaluation_repo.get_workflow_evaluations_by_site_evaluation_id(site_evaluation_id)
        
        return {
            **site_evaluation,
            "node_evaluations": node_evaluations,
            "edge_evaluations": edge_evaluations,
            "workflow_evaluations": workflow_evaluations,
        }
    
    def get_evaluation_by_id(self, evaluation_id: UUID, include_details: bool = True) -> Optional[Dict]:
        """
        평가 ID로 평가 결과 조회
        
        Args:
            evaluation_id: 평가 ID
            include_details: 상세 정보 포함 여부
        
        Returns:
            평가 결과 딕셔너리 또는 None
        """
        site_evaluation = self.evaluation_repo.get_site_evaluation_by_id(evaluation_id)
        if not site_evaluation:
            return None
        
        if not include_details:
            return site_evaluation
        
        # 상세 정보 포함
        site_evaluation_id = UUID(site_evaluation["id"])
        
        # 노드 평가 목록
        node_evaluations = self.evaluation_repo.get_node_evaluations_by_site_evaluation_id(site_evaluation_id)
        
        # 엣지 평가 목록
        edge_evaluations = self.evaluation_repo.get_edge_evaluations_by_site_evaluation_id(site_evaluation_id)
        
        # 워크플로우 평가 목록
        workflow_evaluations = self.evaluation_repo.get_workflow_evaluations_by_site_evaluation_id(site_evaluation_id)
        
        return {
            **site_evaluation,
            "node_evaluations": node_evaluations,
            "edge_evaluations": edge_evaluations,
            "workflow_evaluations": workflow_evaluations,
        }
    
    def get_node_evaluation(self, site_evaluation_id: UUID, node_id: UUID) -> Optional[Dict]:
        """
        노드 평가 조회
        
        Args:
            site_evaluation_id: 사이트 평가 ID
            node_id: 노드 ID
        
        Returns:
            노드 평가 정보 딕셔너리 또는 None
        """
        return self.evaluation_repo.get_node_evaluation_by_node_id(site_evaluation_id, node_id)
    
    def get_edge_evaluation(self, site_evaluation_id: UUID, edge_id: UUID) -> Optional[Dict]:
        """
        엣지 평가 조회
        
        Args:
            site_evaluation_id: 사이트 평가 ID
            edge_id: 엣지 ID
        
        Returns:
            엣지 평가 정보 딕셔너리 또는 None
        """
        return self.evaluation_repo.get_edge_evaluation_by_edge_id(site_evaluation_id, edge_id)


# 하위 호환성을 위한 함수 래퍼
_site_evaluation_service_instance: Optional[SiteEvaluationService] = None


def _get_site_evaluation_service() -> SiteEvaluationService:
    """싱글톤 SiteEvaluationService 인스턴스 반환"""
    global _site_evaluation_service_instance
    if _site_evaluation_service_instance is None:
        _site_evaluation_service_instance = SiteEvaluationService()
    return _site_evaluation_service_instance


def save_evaluation(run_id: UUID, evaluation_data: Dict) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_site_evaluation_service().save_evaluation(run_id, evaluation_data)


def get_evaluation_by_run_id(run_id: UUID, include_details: bool = True) -> Optional[Dict]:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_site_evaluation_service().get_evaluation_by_run_id(run_id, include_details)


def get_evaluation_by_id(evaluation_id: UUID, include_details: bool = True) -> Optional[Dict]:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_site_evaluation_service().get_evaluation_by_id(evaluation_id, include_details)
