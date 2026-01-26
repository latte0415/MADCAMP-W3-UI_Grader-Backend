"""분산 락 관리 유틸리티"""
import time
from typing import Optional
from uuid import UUID
from contextlib import contextmanager

try:
    import redis
    from workers.broker import broker
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class LockManager:
    """분산 락 관리자 (Redis 기반)"""
    
    def __init__(self):
        self.redis_client = None
        if REDIS_AVAILABLE:
            try:
                # broker에서 Redis 클라이언트 가져오기
                if hasattr(broker, 'client'):
                    self.redis_client = broker.client
                else:
                    # 직접 Redis 연결 시도
                    import os
                    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                    self.redis_client = redis.from_url(redis_url)
            except Exception as e:
                print(f"[LockManager] Redis 연결 실패: {e}")
                self.redis_client = None
    
    def acquire_lock(
        self,
        key: str,
        timeout: int = 30,
        retry_interval: float = 0.1,
        max_retries: int = 10
    ) -> bool:
        """
        락 획득 시도
        
        Args:
            key: 락 키
            timeout: 락 만료 시간 (초)
            retry_interval: 재시도 간격 (초)
            max_retries: 최대 재시도 횟수
        
        Returns:
            락 획득 성공 여부
        """
        if not self.redis_client:
            # Redis가 없으면 락 없이 진행 (DB 제약조건에만 의존)
            return True
        
        lock_key = f"lock:{key}"
        retries = 0
        
        while retries < max_retries:
            try:
                # SET NX EX: 키가 없으면 설정하고 만료 시간 설정
                result = self.redis_client.set(
                    lock_key,
                    "locked",
                    nx=True,
                    ex=timeout
                )
                if result:
                    return True
                
                # 락 획득 실패 시 재시도
                time.sleep(retry_interval)
                retries += 1
            except Exception as e:
                print(f"[LockManager] 락 획득 시도 중 에러: {e}")
                return False
        
        return False
    
    def release_lock(self, key: str) -> bool:
        """
        락 해제
        
        Args:
            key: 락 키
        
        Returns:
            락 해제 성공 여부
        """
        if not self.redis_client:
            return True
        
        lock_key = f"lock:{key}"
        try:
            self.redis_client.delete(lock_key)
            return True
        except Exception as e:
            print(f"[LockManager] 락 해제 중 에러: {e}")
            return False
    
    @contextmanager
    def lock(self, key: str, timeout: int = 30):
        """
        컨텍스트 매니저로 락 사용
        
        Args:
            key: 락 키
            timeout: 락 만료 시간 (초)
        
        Yields:
            락 획득 여부
        """
        acquired = self.acquire_lock(key, timeout)
        try:
            yield acquired
        finally:
            if acquired:
                self.release_lock(key)


# 싱글톤 인스턴스
_lock_manager: Optional[LockManager] = None


def get_lock_manager() -> LockManager:
    """LockManager 싱글톤 인스턴스 반환"""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = LockManager()
    return _lock_manager


def acquire_node_lock(run_id: UUID, node_id: UUID, timeout: int = 30) -> bool:
    """
    노드 처리 락 획득
    
    Args:
        run_id: 탐색 세션 ID
        node_id: 노드 ID
        timeout: 락 만료 시간 (초)
    
    Returns:
        락 획득 성공 여부
    """
    lock_manager = get_lock_manager()
    key = f"node:{run_id}:{node_id}"
    return lock_manager.acquire_lock(key, timeout)


def release_node_lock(run_id: UUID, node_id: UUID) -> bool:
    """
    노드 처리 락 해제
    
    Args:
        run_id: 탐색 세션 ID
        node_id: 노드 ID
    
    Returns:
        락 해제 성공 여부
    """
    lock_manager = get_lock_manager()
    key = f"node:{run_id}:{node_id}"
    return lock_manager.release_lock(key)


def acquire_action_lock(
    run_id: UUID,
    from_node_id: UUID,
    action_type: str,
    action_target: str,
    action_value: str = "",
    timeout: int = 30
) -> bool:
    """
    액션 처리 락 획득
    
    Args:
        run_id: 탐색 세션 ID
        from_node_id: 시작 노드 ID
        action_type: 액션 타입
        action_target: 액션 대상
        action_value: 액션 값
        timeout: 락 만료 시간 (초)
    
    Returns:
        락 획득 성공 여부
    """
    lock_manager = get_lock_manager()
    key = f"action:{run_id}:{from_node_id}:{action_type}:{action_target}:{action_value}"
    return lock_manager.acquire_lock(key, timeout)


def release_action_lock(
    run_id: UUID,
    from_node_id: UUID,
    action_type: str,
    action_target: str,
    action_value: str = ""
) -> bool:
    """
    액션 처리 락 해제
    
    Args:
        run_id: 탐색 세션 ID
        from_node_id: 시작 노드 ID
        action_type: 액션 타입
        action_target: 액션 대상
        action_value: 액션 값
    
    Returns:
        락 해제 성공 여부
    """
    lock_manager = get_lock_manager()
    key = f"action:{run_id}:{from_node_id}:{action_type}:{action_target}:{action_value}"
    return lock_manager.release_lock(key)
