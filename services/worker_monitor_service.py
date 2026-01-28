"""워커 모니터링 서비스
Dramatiq 워커 상태를 조회하는 서비스
"""
import os
import json
import pickle
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
        self.broker = None
        if REDIS_AVAILABLE:
            try:
                # broker에서 Redis 클라이언트 가져오기
                if hasattr(broker, 'client'):
                    self.redis_client = broker.client
                elif hasattr(broker, '_client'):
                    self.redis_client = broker._client
                else:
                    # 직접 Redis 연결 시도
                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                    self.redis_client = redis.from_url(redis_url)
                
                self.broker = broker
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
            # broker API를 통해 조회 시도
            if self.broker and hasattr(self.broker, 'get_actor_message_count'):
                try:
                    return self.broker.get_actor_message_count(actor_name)
                except:
                    pass
            
            # 직접 Redis에서 조회
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
        
        messages = []
        
        try:
            # 방법 1: dramatiq:processing:{queue_name}:* 패턴으로 찾기
            pattern = f"dramatiq:processing:{actor_name}:*"
            keys = self.redis_client.keys(pattern)
            
            for key in keys:
                try:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    message_data = self.redis_client.get(key)
                    if message_data:
                        messages.append({
                            "key": key_str,
                            "data": message_data
                        })
                except Exception as e:
                    logger.debug(f"메시지 조회 실패 (key={key}): {e}")
            
            # 방법 2: 모든 dramatiq:processing:* 키 스캔 (더 포괄적)
            if not messages:
                all_processing_pattern = "dramatiq:processing:*"
                all_keys = self.redis_client.keys(all_processing_pattern)
                
                for key in all_keys:
                    try:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        # actor_name과 관련된 키만 필터링
                        if actor_name in key_str:
                            message_data = self.redis_client.get(key)
                            if message_data:
                                messages.append({
                                    "key": key_str,
                                    "data": message_data
                                })
                    except Exception as e:
                        logger.debug(f"메시지 조회 실패 (key={key}): {e}")
            
            # 방법 3: 큐의 첫 번째 메시지를 peek하여 처리 중인지 확인
            # (주의: 실제로는 큐에서 가져온 후 처리 중이므로 이 방법은 제한적)
            
        except Exception as e:
            logger.warning(f"처리 중인 메시지 조회 실패: {e}", exc_info=True)
        
        return messages
    
    def _parse_message_data(self, message_data: Any) -> Optional[Dict[str, Any]]:
        """
        메시지 데이터를 파싱하여 run_id와 기타 정보 추출
        
        Args:
            message_data: Redis에서 가져온 메시지 데이터
        
        Returns:
            파싱된 메시지 정보 딕셔너리 또는 None
        """
        try:
            parsed = None
            
            # bytes인 경우 decode 시도
            if isinstance(message_data, bytes):
                try:
                    # pickle로 직렬화된 경우
                    parsed = pickle.loads(message_data)
                except:
                    try:
                        # JSON인 경우
                        parsed = json.loads(message_data.decode('utf-8'))
                    except:
                        pass
            elif isinstance(message_data, str):
                try:
                    parsed = json.loads(message_data)
                except:
                    pass
            else:
                parsed = message_data
            
            if isinstance(parsed, dict):
                # dramatiq 메시지 형식에서 run_id 추출
                run_id = (
                    parsed.get("kwargs", {}).get("run_id") or 
                    parsed.get("run_id")
                )
                
                # args에서도 run_id 찾기 시도
                if not run_id and isinstance(parsed.get("args"), list) and len(parsed.get("args", [])) > 0:
                    first_arg = parsed["args"][0]
                    if isinstance(first_arg, str):
                        try:
                            UUID(first_arg)
                            run_id = first_arg
                        except:
                            pass
                
                return {
                    "run_id": str(run_id) if run_id else None,
                    "actor_name": parsed.get("actor_name"),
                    "message_id": parsed.get("message_id"),
                    "parsed": parsed
                }
        except Exception as e:
            logger.debug(f"메시지 파싱 실패: {e}")
        
        return None
    
    def get_queue_messages_preview(self, actor_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        큐의 메시지를 peek하여 미리보기 (소비하지 않음)
        
        Args:
            actor_name: actor 이름
            limit: 조회할 최대 메시지 수
        
        Returns:
            큐의 메시지 리스트
        """
        if not self.redis_client:
            return []
        
        try:
            queue_key = f"dramatiq:queue:{actor_name}"
            # LRANGE를 사용하여 메시지를 peek (소비하지 않음)
            messages_data = self.redis_client.lrange(queue_key, 0, limit - 1)
            
            messages = []
            for msg_data in messages_data:
                parsed = self._parse_message_data(msg_data)
                if parsed:
                    messages.append(parsed)
            
            return messages
        except Exception as e:
            logger.warning(f"큐 메시지 미리보기 실패: {e}", exc_info=True)
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
            # "process_action_worker", # Deprecated
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
                
                # 메시지 파싱
                parsed = self._parse_message_data(msg_data)
                
                run_id = parsed.get("run_id") if parsed else None
                task_type = parsed.get("actor_name") if parsed else actor_name
                
                task = {
                    "worker_id": worker_id,
                    "worker_name": worker_id,  # 대체 필드명
                    "type": task_type,
                    "action_type": task_type,  # 대체 필드명
                    "task_type": task_type,  # 대체 필드명
                }
                
                if run_id:
                    task["run_id"] = str(run_id)
                
                processing_tasks.append(task)
        
        # 큐에 있는 메시지도 처리 중인 것으로 간주하여 추가 정보 제공
        queue_tasks = []
        for actor_name in actors:
            queue_messages = self.get_queue_messages_preview(actor_name, limit=5)
            for msg_info in queue_messages:
                if msg_info and msg_info.get("run_id"):
                    queue_tasks.append({
                        "worker_id": f"queue_{actor_name}",
                        "worker_name": f"queue_{actor_name}",
                        "type": actor_name,
                        "action_type": actor_name,
                        "task_type": actor_name,
                        "run_id": msg_info["run_id"],
                        "status": "queued"  # 큐에 대기 중
                    })
        
        return {
            "summary": {
                "total_enqueued": total_enqueued,
                "total_delayed": total_delayed,
                "total_processing": total_processing,
                "total_workers": len(processing_tasks) + len(queue_tasks)
            },
            "actors": actors_status,
            "processing_tasks": processing_tasks + queue_tasks,
            "processing": processing_tasks + queue_tasks,  # 대체 필드명
            "queued_tasks": queue_tasks  # 큐에 있는 작업들
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
            # "process_action_worker", # Deprecated
            "process_pending_actions_worker"
        ]
        
        for actor_name in actors:
            processing_messages = self.get_processing_messages(actor_name)
            for msg in processing_messages:
                # 메시지 데이터에서 run_id 검색
                msg_data = msg.get("data", "")
                msg_key = msg.get("key", "")
                
                # 메시지 파싱
                parsed = self._parse_message_data(msg_data)
                
                # run_id가 일치하는지 확인
                msg_run_id = parsed.get("run_id") if parsed else None
                
                # 문자열 검색으로도 확인
                if (msg_run_id and str(msg_run_id) == run_id_str) or run_id_str in str(msg_data) or run_id_str in str(msg_key):
                    worker_id = msg_key.split(":")[-1] if ":" in msg_key else msg_key
                    
                    current_task = {
                        "type": parsed.get("actor_name") if parsed else actor_name,
                        "action_type": parsed.get("actor_name") if parsed else actor_name,
                        "task_type": parsed.get("actor_name") if parsed else actor_name
                    }
                    
                    run_related_workers.append({
                        "worker_id": worker_id,
                        "worker_name": worker_id,  # 대체 필드명
                        "worker_type": actor_name,
                        "status": "processing",
                        "run_id": str(run_id),
                        "current_task": current_task
                    })
            
            # 큐에 있는 메시지도 확인
            queue_messages = self.get_queue_messages_preview(actor_name, limit=10)
            for msg_info in queue_messages:
                if msg_info and msg_info.get("run_id") == run_id_str:
                    run_related_workers.append({
                        "worker_id": f"queue_{actor_name}",
                        "worker_name": f"queue_{actor_name}",
                        "worker_type": actor_name,
                        "status": "queued",
                        "run_id": str(run_id),
                        "current_task": {
                            "type": msg_info.get("actor_name") or actor_name,
                            "action_type": msg_info.get("actor_name") or actor_name,
                            "task_type": msg_info.get("actor_name") or actor_name
                        }
                    })
        
        return {
            "related_workers": {
                "processing_count": len(run_related_workers)
            },
            "workers": run_related_workers
        }
