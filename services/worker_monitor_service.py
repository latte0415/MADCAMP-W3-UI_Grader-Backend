"""워커 모니터링 서비스
Dramatiq 워커 상태를 조회하는 서비스
"""
import os
from typing import Dict, List, Optional, Any
from uuid import UUID

try:
    import redis
    from workers.broker import broker
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from utils.logger import get_logger

logger = get_logger(__name__)


class WorkerMonitorService:
    """워커 상태 모니터링 서비스"""
    
    def __init__(self):
        self.redis_client = None
        if REDIS_AVAILABLE:
            try:
                # broker에서 Redis 클라이언트 가져오기
                if hasattr(broker, 'client'):
                    self.redis_client = broker.client
                else:
                    # 직접 Redis 연결 시도
                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                    self.redis_client = redis.from_url(redis_url)
            except Exception as e:
                logger.warning(f"Redis 연결 실패: {e}", exc_info=True)
                self.redis_client = None
    
    def get_queue_message_count(self, actor_name: str) -> int:
        """
        큐에 대기 중인 메시지 수 조회
        
        Args:
            actor_name: actor 이름 (예: "process_node_worker")
        
        Returns:
            대기 중인 메시지 수
        """
        if not self.redis_client:
            return 0
        
        try:
            queue_key = f"dramatiq:queue:{actor_name}"
            return self.redis_client.llen(queue_key)
        except Exception as e:
            logger.warning(f"큐 메시지 수 조회 실패: {e}", exc_info=True)
            return 0
    
    def get_delay_message_count(self, actor_name: str) -> int:
        """
        지연된 메시지 수 조회
        
        Args:
            actor_name: actor 이름
        
        Returns:
            지연된 메시지 수
        """
        if not self.redis_client:
            return 0
        
        try:
            delay_key = f"dramatiq:delay:{actor_name}"
            return self.redis_client.zcard(delay_key)
        except Exception as e:
            logger.warning(f"지연 메시지 수 조회 실패: {e}", exc_info=True)
            return 0
    
    def get_processing_messages(self, actor_name: str) -> List[Dict[str, Any]]:
        """
        처리 중인 메시지 조회
        
        Args:
            actor_name: actor 이름
        
        Returns:
            처리 중인 메시지 리스트
        """
        if not self.redis_client:
            return []
        
        try:
            # Dramatiq는 처리 중인 메시지를 특정 키 패턴으로 저장
            # 정확한 키 패턴은 Dramatiq 버전에 따라 다를 수 있음
            processing_key = f"dramatiq:processing:{actor_name}"
            messages = []
            
            # 처리 중인 메시지 키들을 찾기
            pattern = f"dramatiq:processing:{actor_name}:*"
            keys = self.redis_client.keys(pattern)
            
            for key in keys:
                try:
                    message_data = self.redis_client.get(key)
                    if message_data:
                        # 메시지 데이터 파싱 (실제 구현은 Dramatiq의 내부 형식에 따라 달라질 수 있음)
                        messages.append({
                            "key": key.decode() if isinstance(key, bytes) else key,
                            "data": message_data.decode() if isinstance(message_data, bytes) else message_data
                        })
                except Exception as e:
                    logger.warning(f"메시지 파싱 실패: {e}", exc_info=True)
            
            return messages
        except Exception as e:
            logger.warning(f"처리 중인 메시지 조회 실패: {e}", exc_info=True)
            return []
    
    def get_actor_status(self, actor_name: str) -> Dict[str, Any]:
        """
        특정 actor의 상태 조회
        
        Args:
            actor_name: actor 이름
        
        Returns:
            actor 상태 딕셔너리
        """
        return {
            "enqueued": self.get_queue_message_count(actor_name),
            "delayed": self.get_delay_message_count(actor_name),
            "processing": len(self.get_processing_messages(actor_name))
        }
    
    def get_all_workers_status(self) -> Dict[str, Any]:
        """
        모든 워커 상태 조회
        
        Returns:
            전체 워커 상태 딕셔너리 (프론트엔드 스펙 형식: summary, actors, processing_tasks)
        """
        actors = [
            "process_node_worker",
            "process_action_worker",
            "process_pending_actions_worker"
        ]
        
        actors_status = {}
        total_enqueued = 0
        total_delayed = 0
        total_processing = 0
        processing_tasks = []
        
        for actor_name in actors:
            status = self.get_actor_status(actor_name)
            actors_status[actor_name] = status
            total_enqueued += status["enqueued"]
            total_delayed += status["delayed"]
            total_processing += status["processing"]
            
            # 처리 중인 작업 목록 수집
            processing_messages = self.get_processing_messages(actor_name)
            for msg in processing_messages:
                msg_key = msg.get("key", "")
                msg_data = msg.get("data", "")
                
                # 메시지에서 정보 추출 시도
                worker_id = msg_key.split(":")[-1] if ":" in msg_key else msg_key
                
                # 메시지 데이터에서 run_id 추출 시도
                run_id = None
                task_type = None
                if isinstance(msg_data, str):
                    # JSON 문자열인 경우 파싱 시도
                    try:
                        import json
                        parsed = json.loads(msg_data)
                        if isinstance(parsed, dict):
                            run_id = parsed.get("kwargs", {}).get("run_id") or parsed.get("run_id")
                            task_type = parsed.get("actor_name") or actor_name
                    except:
                        # JSON이 아니면 문자열에서 run_id 검색
                        if "run_id" in msg_data:
                            # 간단한 추출 시도
                            pass
                
                task = {
                    "worker_id": worker_id,
                    "worker_name": worker_id,  # 대체 필드명
                    "type": task_type or actor_name,
                    "action_type": task_type or actor_name,  # 대체 필드명
                    "task_type": task_type or actor_name,  # 대체 필드명
                }
                
                if run_id:
                    task["run_id"] = str(run_id)
                
                # 원본 메시지 데이터도 포함 (디버깅용)
                task["_raw_data"] = str(msg_data)[:200]  # 최대 200자만
                
                processing_tasks.append(task)
        
        return {
            "summary": {
                "total_enqueued": total_enqueued,
                "total_delayed": total_delayed,
                "total_processing": total_processing,
                "total_workers": len(processing_tasks)
            },
            "actors": actors_status,
            "processing_tasks": processing_tasks,
            "processing": processing_tasks  # 대체 필드명
        }
    
    def get_run_worker_status(self, run_id: UUID) -> Dict[str, Any]:
        """
        특정 run_id와 관련된 워커 상태 조회
        
        Args:
            run_id: 탐색 세션 ID
        
        Returns:
            run_id 관련 워커 상태 딕셔너리 (프론트엔드 스펙 형식: related_workers, workers)
        
        Note:
            실제 구현에서는 메시지 내용을 파싱하여 run_id를 추출해야 함
        """
        # run_id와 관련된 처리 중인 메시지 찾기
        run_related_workers = []
        run_id_str = str(run_id)
        
        actors = [
            "process_node_worker",
            "process_action_worker",
            "process_pending_actions_worker"
        ]
        
        for actor_name in actors:
            processing_messages = self.get_processing_messages(actor_name)
            for msg in processing_messages:
                # 메시지 데이터에서 run_id 검색
                msg_data = msg.get("data", "")
                msg_key = msg.get("key", "")
                
                # 메시지 데이터 파싱 시도
                current_task = None
                if isinstance(msg_data, str):
                    try:
                        import json
                        parsed = json.loads(msg_data)
                        if isinstance(parsed, dict):
                            msg_run_id = parsed.get("kwargs", {}).get("run_id") or parsed.get("run_id")
                            if str(msg_run_id) == run_id_str:
                                current_task = {
                                    "type": parsed.get("actor_name") or actor_name,
                                    "action_type": parsed.get("actor_name") or actor_name,
                                    "task_type": parsed.get("actor_name") or actor_name,
                                    "_raw": parsed
                                }
                    except:
                        pass
                
                # 문자열 검색으로도 확인
                if run_id_str in str(msg_data) or run_id_str in str(msg_key):
                    worker_id = msg_key.split(":")[-1] if ":" in msg_key else msg_key
                    
                    # current_task가 없으면 기본값 생성
                    if not current_task:
                        current_task = {
                            "type": actor_name,
                            "action_type": actor_name,
                            "task_type": actor_name
                        }
                    
                    run_related_workers.append({
                        "worker_id": worker_id,
                        "worker_name": worker_id,  # 대체 필드명
                        "worker_type": actor_name,
                        "status": "processing",
                        "run_id": str(run_id),
                        "current_task": current_task
                    })
        
        return {
            "related_workers": {
                "processing_count": len(run_related_workers)
            },
            "workers": run_related_workers
        }
