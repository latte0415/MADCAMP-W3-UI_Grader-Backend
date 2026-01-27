"""엣지(액션) 서비스"""
import time
import asyncio
from typing import Dict, Optional
from uuid import UUID
from playwright.async_api import Page

from repositories import edge_repository
from repositories import node_repository
from services.ai_service import AiService
from utils.graph_classifier import classify_change, compute_next_depths
from utils.action_extractor import parse_action_target
from exceptions.service import ActionExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)


class EdgeService:
    """엣지 관련 비즈니스 로직"""
    
    def __init__(self, edge_repo=None, node_repo=None, node_service=None):
        """
        Args:
            edge_repo: EdgeRepository 모듈 (기본값: edge_repository)
            node_repo: NodeRepository 모듈 (기본값: node_repository)
            node_service: NodeService 인스턴스 (선택적)
        """
        self.edge_repo = edge_repo or edge_repository
        self.node_repo = node_repo or node_repository
        self.node_service = node_service
    
    def is_duplicate_action(self, run_id: UUID, from_node_id: UUID, action: Dict) -> Optional[Dict]:
        """
        중복 액션 여부 확인 (성공한 엣지만 체크)
        
        Args:
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
            action: 액션 딕셔너리
        
        Returns:
            기존 엣지 데이터 또는 None (성공한 엣지만 반환)
        """
        action_value = action.get("action_value", "") or ""
        # 성공한 엣지만 중복으로 체크 (실패한 액션은 재시도 허용)
        return self.edge_repo.find_duplicate_edge(
            run_id,
            from_node_id,
            action["action_type"],
            action["action_target"],
            action_value,
            outcome="success"  # 성공한 엣지만 중복으로 체크
        )
    
    async def perform_action(self, page: Page, action: Dict) -> Dict:
        """
        액션 수행
        
        Args:
            page: Playwright Page 객체
            action: 액션 딕셔너리
        
        Returns:
            {outcome, latency_ms, error_msg}
        """
        start_time = time.time()
        error_msg = None
        outcome = "success"
        
        try:
            action_type = action["action_type"]
            action_value = action.get("action_value", "")
            role = action.get("role")
            name = action.get("name")
            selector = action.get("selector")
            
            if action_type == "click":
                href = action.get("href")
                before_url = page.url  # 클릭 전 URL 저장
                # role과 name이 있으면 우선 사용 (가장 정확함)
                if role and name:
                    locator = page.get_by_role(role, name=name)
                    await locator.evaluate("el => el.scrollIntoView({block: 'center'})")
                    try:
                        await locator.click(force=True, timeout=5000)
                    except Exception:
                        # viewport 이슈 fallback: JS click
                        await locator.evaluate("el => el.click()")
                elif selector:
                    await page.wait_for_selector(selector, timeout=5000, state="attached")
                    locator = page.locator(selector).first
                    await locator.evaluate("el => el.scrollIntoView({block: 'center'})")
                    try:
                        await locator.click(force=True, timeout=5000)
                    except Exception:
                        # viewport 이슈 fallback: JS click
                        await locator.evaluate("el => el.click()")
                else:
                    raise Exception("click: 대상 요소를 찾을 수 없습니다.")
                # URL 변경이 없으면 href로 직접 이동 시도
                if href and page.url == before_url:
                    await page.goto(href, wait_until="networkidle")
                # SPA에서 URL 변화 없이 DOM만 바뀌는 케이스 대비
                # 네트워크 상태가 안정화될 때까지 대기 (타임아웃 명시)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)  # 5초 → 10초로 증가
                except Exception:
                    # 타임아웃이어도 계속 진행 (일부 페이지는 networkidle에 도달하지 않을 수 있음)
                    pass
                # 추가 안정화 대기 시간 (최적화: 1500ms → 1000ms)
                await page.wait_for_timeout(1000)
            elif action_type == "hover":
                if role and name:
                    await page.get_by_role(role, name=name).hover()
                elif selector:
                    await page.hover(selector)
                else:
                    raise Exception("hover: 대상 요소를 찾을 수 없습니다.")
                await page.wait_for_timeout(400)
            elif action_type == "fill":
                filled_element = None
                filled_locator = None
                # role과 name이 있으면 우선 사용 (가장 정확함)
                if role and name:
                    try:
                        locator = page.get_by_role(role, name=name)
                        # 요소가 정확히 하나인지 확인
                        count = await locator.count()
                        if count == 1:
                            filled_element = await locator.element_handle()
                            filled_locator = locator
                            await locator.fill(action_value)
                        elif count > 1:
                            # 여러 요소가 있으면 첫 번째 사용
                            filled_locator = locator.first
                            filled_element = await filled_locator.element_handle()
                            await filled_locator.fill(action_value)
                        else:
                            raise Exception(f"fill: role={role} name={name}로 요소를 찾을 수 없습니다.")
                    except Exception as e:
                        # role+name 실패 시 action_target 파싱 시도
                        action_target = action.get("action_target", "")
                        parsed_role, parsed_name = parse_action_target(action_target)
                        if parsed_role and parsed_name:
                            locator = page.get_by_role(parsed_role, name=parsed_name)
                            count = await locator.count()
                            if count == 1:
                                filled_element = await locator.element_handle()
                                filled_locator = locator
                                await locator.fill(action_value)
                            elif count > 1:
                                filled_locator = locator.first
                                filled_element = await filled_locator.element_handle()
                                await filled_locator.fill(action_value)
                            else:
                                raise Exception(f"fill: action_target 파싱으로도 요소를 찾을 수 없습니다.")
                        elif selector:
                            # 마지막 수단: selector 사용
                            filled_locator = page.locator(selector).first
                            filled_element = await filled_locator.element_handle()
                            await page.fill(selector, action_value)
                        else:
                            raise Exception("fill: 대상 요소를 찾을 수 없습니다.")
                # role과 name이 없으면 action_target 파싱 시도
                elif not role and not name:
                    action_target = action.get("action_target", "")
                    parsed_role, parsed_name = parse_action_target(action_target)
                    if parsed_role and parsed_name:
                        locator = page.get_by_role(parsed_role, name=parsed_name)
                        count = await locator.count()
                        if count == 1:
                            filled_element = await locator.element_handle()
                            filled_locator = locator
                            await locator.fill(action_value)
                        elif count > 1:
                            filled_locator = locator.first
                            filled_element = await filled_locator.element_handle()
                            await filled_locator.fill(action_value)
                        else:
                            if selector:
                                filled_locator = page.locator(selector).first
                                filled_element = await filled_locator.element_handle()
                                await page.fill(selector, action_value)
                            else:
                                raise Exception("fill: 대상 요소를 찾을 수 없습니다.")
                    elif selector:
                        # 마지막 수단: selector 사용
                        filled_locator = page.locator(selector).first
                        filled_element = await filled_locator.element_handle()
                        await page.fill(selector, action_value)
                    else:
                        raise Exception("fill: 대상 요소를 찾을 수 없습니다.")
                # selector만 있는 경우
                elif selector:
                    filled_locator = page.locator(selector).first
                    filled_element = await filled_locator.element_handle()
                    await page.fill(selector, action_value)
                else:
                    raise Exception("fill: 대상 요소를 찾을 수 없습니다.")
                
                # fill 액션 후 입력 이벤트가 처리되고 페이지가 안정화될 때까지 대기
                # React 같은 프레임워크에서 상태 업데이트를 위해 충분한 대기 시간 필요
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    # 타임아웃이어도 계속 진행
                    pass
                
                # 입력값이 실제로 반영되었는지 확인
                # React 같은 프레임워크의 경우 상태 업데이트를 기다리기 위해 최대 2초 대기
                max_wait_time = 2000  # 2초
                wait_interval = 100  # 100ms마다 확인
                waited = 0
                value_matched = False
                
                # 입력 필드의 값이 실제로 변경되었는지 확인
                if filled_element:
                    try:
                        while waited < max_wait_time:
                            current_value = await filled_element.evaluate("el => el.value")
                            if current_value == action_value:
                                value_matched = True
                                break
                            await asyncio.sleep(wait_interval / 1000)
                            waited += wait_interval
                    except Exception:
                        # 확인 실패 시 계속 진행
                        pass
                
                # 추가 안정화 대기 시간 (입력 후 폼 검증, 버튼 활성화 등이 실행될 수 있음)
                # React 같은 프레임워크에서는 상태 업데이트가 비동기로 일어날 수 있으므로 충분한 대기 필요
                if value_matched:
                    # 값이 반영되었으면 폼 검증 완료를 위해 추가 대기
                    await page.wait_for_timeout(800)  # 800ms 대기
                else:
                    # 값이 반영되지 않았어도 최소 대기
                    await page.wait_for_timeout(500)  # 500ms 대기
                
                # 비밀번호 필드인지 확인 (input_type 확인)
                is_password_field = False
                actual_stored_value = None
                if filled_element:
                    try:
                        input_type = await filled_element.evaluate("el => el.type")
                        is_password_field = (input_type == "password")
                        # 실제로 저장된 값 읽기 (collect_input_values에서 읽을 값과 동일)
                        if is_password_field:
                            actual_stored_value = await filled_element.evaluate("el => el.value")
                    except Exception:
                        # input_type 확인 실패 시 action의 input_type 사용
                        is_password_field = (action.get("input_type", "") == "password")
                
                # latency_ms 계산 (비밀번호 필드인 경우에도 정상적으로 채워야 하므로 여기서 계산)
                latency_ms = int((time.time() - start_time) * 1000)
                
                # 비밀번호 필드인 경우 collect_input_values와 동일한 방식으로 해시화하여 반환 (역해시 딕셔너리용)
                if is_password_field and action_value and actual_stored_value:
                    import hashlib
                    # collect_input_values와 동일한 방식으로 해시화
                    # (실제 저장된 값을 해시화 - collect_input_values에서도 같은 값을 읽어서 해시화함)
                    value_hash = hashlib.sha256(actual_stored_value.encode()).hexdigest()[:16]
                    return {
                        "outcome": outcome,
                        "latency_ms": latency_ms,
                        "error_msg": error_msg,
                        "password_hash": value_hash,  # collect_input_values에서 생성한 해시와 동일한 값
                        "password_value": action_value  # 원본 입력 값 저장 (복원용)
                    }
            elif action_type == "navigate":
                await page.goto(action_value, wait_until="networkidle")
            elif action_type == "wait":
                await page.wait_for_load_state("networkidle")
            else:
                raise Exception(f"알 수 없는 action_type: {action_type}")
        except Exception as e:
            outcome = "fail"
            error_msg = str(e)
            logger.warning(f"액션 실행 실패: {action_type} / {action.get('action_target', 'unknown')} - {error_msg}", exc_info=True)
        
        latency_ms = int((time.time() - start_time) * 1000)
        return {"outcome": outcome, "latency_ms": latency_ms, "error_msg": error_msg}
    
    def record_edge(
        self,
        run_id: UUID,
        from_node_id: UUID,
        to_node_id: Optional[UUID],
        action: Dict,
        outcome: str,
        latency_ms: int,
        error_msg: Optional[str] = None,
        depth_diff_type: Optional[str] = None
    ) -> Dict:
        """
        엣지 기록 (중복 검사 포함)
        
        Args:
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
            to_node_id: 종료 노드 ID (선택적)
            action: 액션 딕셔너리
            outcome: 결과 ('success' 또는 'fail')
            latency_ms: 지연 시간 (밀리초)
            error_msg: 에러 메시지 (선택적)
            depth_diff_type: depth 차이 타입 (선택적)
        
        Returns:
            엣지 정보 딕셔너리
        """
        # record_edge 호출 시점에서도 중복 체크 (안전장치)
        existing = self.is_duplicate_action(run_id, from_node_id, action)
        if existing:
            logger.debug(f"중복 액션 발견 (record_edge 시점): run_id={run_id}, from_node={from_node_id}, action={action.get('action_type')} / {action.get('action_target', '')[:50]}, existing_edge_id={existing.get('id')}")
            return existing
        
        action_value = action.get("action_value", "") or ""
        edge_data = {
            "run_id": str(run_id),
            "from_node_id": str(from_node_id),
            "to_node_id": str(to_node_id) if to_node_id else None,
            "action_type": action["action_type"],
            "action_target": action["action_target"],
            "action_value": action_value,
            "cost": action.get("cost", 1),
            "latency_ms": latency_ms,
            "outcome": outcome,
            "error_msg": error_msg,
            "depth_diff_type": depth_diff_type
        }
        
        try:
            edge = self.edge_repo.create_edge(edge_data)
            logger.debug(f"엣지 생성 성공: edge_id={edge.get('id')}, run_id={run_id}, from_node={from_node_id}, to_node={to_node_id}, outcome={outcome}")
            return edge
        except Exception as e:
            logger.error(f"엣지 생성 실패: run_id={run_id}, from_node={from_node_id}, action={action.get('action_type')} / {action.get('action_target', '')[:50]}, error={e}", exc_info=True)
            # 엣지 생성 실패 시에도 중복 체크를 다시 수행 (다른 워커가 생성했을 수 있음)
            existing_after_fail = self.is_duplicate_action(run_id, from_node_id, action)
            if existing_after_fail:
                logger.info(f"엣지 생성 실패 후 중복 엣지 발견: existing_edge_id={existing_after_fail.get('id')}")
                return existing_after_fail
            raise
    
    async def perform_and_record_edge(
        self,
        run_id: UUID,
        from_node_id: UUID,
        page: Page,
        action: Dict,
        depth_diff_type: Optional[str] = None
    ) -> Dict:
        """
        액션 수행 후 엣지 기록
        
        Args:
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
            page: Playwright Page 객체
            action: 액션 딕셔너리
            depth_diff_type: depth 차이 타입 (선택적)
        
        Returns:
            엣지 정보 딕셔너리
        """
        # 워커 생성 시점과 실행 시점 사이에 다른 워커가 같은 액션을 실행했을 수 있으므로
        # 실행 시점에서 다시 중복 체크를 수행
        existing = self.is_duplicate_action(run_id, from_node_id, action)
        if existing:
            logger.debug(f"중복 액션 발견 (실행 시점): run_id={run_id}, from_node={from_node_id}, action={action.get('action_type')} / {action.get('action_target', '')[:50]}, existing_edge_id={existing.get('id')}")
            return existing
        
        # node_service가 주입된 경우 사용, 없으면 node_repo 직접 사용
        before_node = None
        if self.node_service:
            before_node = self.node_service.get_node_by_id(from_node_id)
        else:
            before_node = self.node_repo.get_node_by_id(from_node_id)
        
        action_result = await self.perform_action(page, action)
        
        # 비밀번호 필드에 값을 채운 경우 역해시 딕셔너리에 저장 (복원용)
        if action_result["outcome"] == "success" and action_result.get("password_hash"):
            try:
                from repositories.ai_memory_repository import view_run_memory, update_run_memory
                run_memory = view_run_memory(run_id)
                content = run_memory.get("content", {})
                
                # password_hash_map 딕셔너리 초기화 (없으면)
                if "password_hash_map" not in content:
                    content["password_hash_map"] = {}
                
                # 해시 값을 키로 사용하여 원본 비밀번호 값 저장 (역해시 딕셔너리)
                password_hash = action_result.get("password_hash")
                password_value = action_result.get("password_value", "")
                if password_hash and password_value:
                    content["password_hash_map"][password_hash] = password_value
                    update_run_memory(run_id, content)
                    logger.debug(f"비밀번호 역해시 딕셔너리 저장: hash={password_hash[:8]}...")
            except Exception as e:
                # 비밀번호 저장 실패는 로그만 남기고 계속 진행 (비치명적 에러)
                logger.warning(f"비밀번호 역해시 딕셔너리 저장 실패 (계속 진행): {e}", exc_info=True)
        
        to_node_id = None
        to_node = None
        to_node_created = False
        if action_result["outcome"] == "success":
            # 액션 실행 후 페이지가 완전히 안정화될 때까지 대기
            # 노드 생성 전에 페이지 상태가 완전히 반영되도록 함
            # 타임아웃을 명시적으로 설정하여 무한 대기 방지
            try:
                # DOM이 로드될 때까지 대기 (최대 10초)
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                # 네트워크가 안정화될 때까지 대기 (최대 10초, 타임아웃 명시)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)  # 5초 → 10초로 증가
                except Exception:
                    # networkidle에 도달하지 않아도 계속 진행 (일부 페이지는 계속 요청을 보낼 수 있음)
                    pass
                
                # 로그인 액션 후 리다이렉트 및 인증 정보 저장을 위한 추가 대기
                # URL이 변경되는 경우 리다이렉트 완료를 기다림
                action_type = action.get("action_type", "")
                if action_type in ["click", "fill"]:
                    # URL 변경 감지 (리다이렉트 완료 확인)
                    initial_url = page.url
                    max_redirect_wait = 5000  # 최대 5초 대기
                    redirect_wait_interval = 100  # 100ms마다 확인
                    redirect_waited = 0
                    
                    while redirect_waited < max_redirect_wait:
                        current_url = page.url
                        if current_url != initial_url:
                            # URL이 변경되었으면 리다이렉트 완료 대기
                            try:
                                await page.wait_for_load_state("networkidle", timeout=5000)
                            except Exception:
                                pass
                            break
                        await asyncio.sleep(redirect_wait_interval / 1000)
                        redirect_waited += redirect_wait_interval
                
                # 추가 안정화 대기 (쿠키/세션 저장 완료 및 페이지 변경이 완전히 반영되도록)
                # 로그인 후 인증 정보 저장을 위해 충분한 대기 시간 필요
                await asyncio.sleep(1.0)  # 0.3초 → 1.0초로 증가 (인증 정보 저장 대기)
            except Exception as e:
                logger.warning(f"페이지 로드 대기 중 에러 (계속 진행): {e}")
            
            if self.node_service:
                result = await self.node_service.create_or_get_node(run_id, page, return_created=True)
                if isinstance(result, tuple):
                    to_node, to_node_created = result
                else:
                    to_node = result
                    to_node_created = False
            else:
                # node_service가 없으면 직접 호출 (하위 호환성)
                from services.node_service import create_or_get_node
                result = await create_or_get_node(run_id, page, return_created=True)
                if isinstance(result, tuple):
                    to_node, to_node_created = result
                else:
                    to_node = result
                    to_node_created = False
            
            to_node_id = UUID(to_node["id"])
            
            # 같은 노드로 돌아온 경우 실패로 간주
            if to_node_id == from_node_id:
                action_result["outcome"] = "fail"
                action_result["error_msg"] = "액션 실행 후 같은 노드로 돌아옴"
                to_node_id = None  # 같은 노드로 돌아온 경우 to_node_id를 None으로 설정
                logger.warning(f"액션 실행 후 같은 노드로 돌아옴: from_node={from_node_id}, action={action.get('action_type')} / {action.get('action_target', '')[:50]}")
            else:
                # 다른 노드로 이동한 경우에만 기존 엣지 삭제 (중복 방지)
                from repositories.edge_repository import find_edge_by_nodes, delete_edge
                existing_edge = find_edge_by_nodes(run_id, from_node_id, to_node_id)
                if existing_edge:
                    # 기존 엣지 삭제 (무효화)
                    delete_edge(UUID(existing_edge["id"]))
        
        if depth_diff_type is None and before_node:
            depth_diff_type = await classify_change(before_node, to_node, page)
        
        if to_node_created and before_node and depth_diff_type:
            depths = compute_next_depths(before_node, depth_diff_type)
            if self.node_service:
                self.node_service.update_node_depths(to_node_id, depths)
            else:
                self.node_repo.update_node_depths(to_node_id, depths)
        
        edge = self.record_edge(
            run_id=run_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            action=action,
            outcome=action_result["outcome"],
            latency_ms=action_result["latency_ms"],
            error_msg=action_result["error_msg"],
            depth_diff_type=depth_diff_type
        )
        
        # 엣지 생성 후 intent_label 생성 (from_node != to_node인 경우만)
        if edge and edge.get("from_node_id") and edge.get("to_node_id") and edge.get("from_node_id") != edge.get("to_node_id"):
            edge_id = UUID(edge["id"])
            # 비동기 작업을 백그라운드에서 실행 (에러 발생 시 로그만 남기고 계속 진행)
            try:
                ai_service = AiService()
                asyncio.create_task(ai_service.guess_and_update_edge_intent(edge_id))
            except Exception as e:
                # 비동기 작업 생성 실패는 로그만 남기고 계속 진행 (비치명적 에러)
                logger.warning(f"intent_label 생성 작업 시작 실패 (계속 진행): {e}", exc_info=True)
        
        return edge


# 하위 호환성을 위한 함수 래퍼
_edge_service_instance: Optional[EdgeService] = None


def _get_edge_service() -> EdgeService:
    """싱글톤 EdgeService 인스턴스 반환"""
    global _edge_service_instance
    if _edge_service_instance is None:
        _edge_service_instance = EdgeService()
    return _edge_service_instance


def is_duplicate_action(run_id: UUID, from_node_id: UUID, action: Dict) -> Optional[Dict]:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_edge_service().is_duplicate_action(run_id, from_node_id, action)


async def perform_action(page: Page, action: Dict) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return await _get_edge_service().perform_action(page, action)


def record_edge(
    run_id: UUID,
    from_node_id: UUID,
    to_node_id: Optional[UUID],
    action: Dict,
    outcome: str,
    latency_ms: int,
    error_msg: Optional[str] = None,
    depth_diff_type: Optional[str] = None
) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return _get_edge_service().record_edge(
        run_id, from_node_id, to_node_id, action, outcome, latency_ms, error_msg, depth_diff_type
    )


async def perform_and_record_edge(
    run_id: UUID,
    from_node_id: UUID,
    page: Page,
    action: Dict,
    depth_diff_type: Optional[str] = None
) -> Dict:
    """하위 호환성을 위한 함수 래퍼"""
    return await _get_edge_service().perform_and_record_edge(
        run_id, from_node_id, page, action, depth_diff_type
    )
