from infra.langchain.config.context import set_run_id, set_from_node_id
from typing import Dict, Optional, Any, List, Tuple
from uuid import UUID

from infra.langchain.runnables.chain import run_chain
        
from repositories.ai_memory_repository import view_run_memory, update_run_memory, delete_pending_action
from repositories.edge_repository import get_edge_by_id, update_edge_intent_label
from repositories.node_repository import get_node_by_id
from services.pending_action_service import PendingActionService
from schemas.filter_action import FilterActionOutput
from schemas.run_memory import UpdateRunMemoryOutput
from schemas.guess_intent import GuessIntentOutput
from exceptions.service import AIServiceError, ModerationError
from exceptions.repository import EntityNotFoundError
from utils.logger import get_logger

logger = get_logger(__name__)

class AiService:
    """AI·체인 관련 서비스 (모든 기능이 chain 기반)."""

    def __init__(self):
        pass

    def _get_run_memory_content(self, run_id: UUID) -> Dict[str, Any]:
        """
        run_memory의 content를 조회합니다.
        
        Args:
            run_id: 탐색 세션 ID
            
        Returns:
            run_memory의 content 딕셔너리 (없으면 빈 딕셔너리)
        """
        run_memory_data = view_run_memory(run_id)
        return run_memory_data.get("content", {}) if run_memory_data else {}

    def _extract_actions_from_result(self, result: Any) -> List[Dict[str, Any]]:
        """
        Chain 결과에서 처리 가능한 액션 리스트를 추출합니다.
        
        Args:
            result: Chain 실행 결과 (FilterActionOutput 또는 dict)
            
        Returns:
            처리 가능한 액션 리스트 (action_value가 채워진 딕셔너리 형태)
        """
        if isinstance(result, FilterActionOutput):
            return [action.model_dump(exclude_none=False) for action in result.actions]
        elif isinstance(result, dict) and "actions" in result:
            return result["actions"]
        else:
            return []

    def _extract_content_from_result(
        self, 
        result: Any, 
        fallback_content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Chain 결과에서 content를 추출합니다.
        
        Args:
            result: Chain 실행 결과 (UpdateRunMemoryOutput 또는 dict)
            fallback_content: 파싱 실패 시 사용할 기본 content
            
        Returns:
            추출된 content 딕셔너리
        """
        if isinstance(result, UpdateRunMemoryOutput):
            return result.content
        elif isinstance(result, dict) and "content" in result:
            return result["content"]
        else:
            return fallback_content

    def _create_action_key(
        self, 
        action: Dict[str, Any], 
        include_selector: bool = True
    ) -> tuple:
        """
        액션을 고유하게 식별하기 위한 키를 생성합니다.
        
        Args:
            action: 액션 딕셔너리
            include_selector: selector, role, name을 키에 포함할지 여부
        
        Returns:
            액션 식별 키 튜플
        """
        if include_selector:
            return (
                action.get("action_type", ""),
                action.get("action_target", ""),
                action.get("selector", ""),
                action.get("role", ""),
                action.get("name", "")
            )
        else:
            return (
                action.get("action_type", ""),
                action.get("action_target", "")
            )

    def _dicts_are_different(
        self,
        old_dict: Dict[str, Any],
        new_dict: Dict[str, Any]
    ) -> bool:
        """
        두 딕셔너리가 다른지 재귀적으로 비교합니다.
        
        Args:
            old_dict: 이전 딕셔너리
            new_dict: 새로운 딕셔너리
        
        Returns:
            다르면 True, 같으면 False
        """
        # 키가 다르면 다름
        if set(old_dict.keys()) != set(new_dict.keys()):
            return True
        
        # 각 값 비교
        for key in old_dict.keys():
            old_value = old_dict[key]
            new_value = new_dict[key]
            
            # 둘 다 딕셔너리면 재귀 비교
            if isinstance(old_value, dict) and isinstance(new_value, dict):
                if self._dicts_are_different(old_value, new_value):
                    return True
            # 둘 다 리스트면 비교
            elif isinstance(old_value, list) and isinstance(new_value, list):
                if len(old_value) != len(new_value):
                    return True
                for i, old_item in enumerate(old_value):
                    if i >= len(new_value):
                        return True
                    new_item = new_value[i]
                    if isinstance(old_item, dict) and isinstance(new_item, dict):
                        if self._dicts_are_different(old_item, new_item):
                            return True
                    elif old_item != new_item:
                        return True
            # 그 외는 직접 비교
            elif old_value != new_value:
                return True
        
        return False

    async def get_ai_response(self) -> str:
        """chat-test chain 실행. Returns: AI 응답 문자열."""
        result = await run_chain(label="chat-test")
        return str(result)

    async def get_ai_response_with_photo(
        self,
        image_base64: str,
        auxiliary_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        이미지와 보조 자료를 포함하여 AI 응답을 받습니다.
        
        Args:
            image_base64: base64로 인코딩된 이미지
            auxiliary_data: 보조 자료 딕셔너리 (사용자가 인지할 수 있는 정보만)
        
        Returns:
            AI 응답 문자열
        """
        result = await run_chain(
            label="photo-test",
            image_base64=image_base64,
            auxiliary_data=auxiliary_data,
            use_vision=True
        )
        return str(result)

    async def update_run_memory_with_ai(
        self,
        run_id: UUID = None,
        auxiliary_data: Optional[Dict[str, Any]] = None,
        page_state: Optional[Dict[str, Any]] = None,
        # image_base64 파라미터는 더 이상 사용하지 않음 (하위 호환성을 위해 유지하되 무시)
        image_base64: Optional[str] = None,
    ) -> Tuple[Dict, bool]:
        """
        페이지 정보를 기반으로 run_memory를 업데이트합니다.
        
        Args:
            run_id: run_id
            auxiliary_data: 보조 자료 딕셔너리 (사용자가 인지할 수 있는 정보만)
            page_state: 페이지 상태 정보 (이미지 대신 사용)
            image_base64: 더 이상 사용하지 않음 (하위 호환성을 위해 유지, 무시됨)
        
        Returns:
            (업데이트된 run_memory 정보 딕셔너리, 수정사항 여부) 튜플
            - 수정사항이 있으면 True, 없으면 False
        """
        # image_base64 파라미터는 더 이상 사용하지 않음 (명시적으로 무시)
        if image_base64 is not None:
            logger.warning("image_base64 파라미터는 더 이상 사용하지 않습니다. 무시됩니다.")
        # 1. 현재 run_memory 조회
        run_memory_content = self._get_run_memory_content(run_id)
        
        # 2. 페이지 상태 정보를 auxiliary_data에 통합 (이미지 대신 사용)
        enhanced_auxiliary_data = auxiliary_data.copy() if auxiliary_data else {}
        
        if page_state:
            # 일반 사용자가 인지할 수 있는 정보만 포함
            # 페이지 제목
            page_title = page_state.get("page_title", "")
            if page_title:
                enhanced_auxiliary_data["page_title"] = page_title
            
            # 제목들 (h1, h2, h3)
            headings = page_state.get("headings", [])
            if headings:
                enhanced_auxiliary_data["headings"] = headings[:10]
            
            # 문단 텍스트
            paragraphs = page_state.get("paragraphs", [])
            if paragraphs:
                enhanced_auxiliary_data["paragraphs"] = paragraphs[:10]
            
            # 버튼 텍스트
            buttons = page_state.get("buttons", [])
            if buttons:
                enhanced_auxiliary_data["buttons"] = buttons[:15]
            
            # 링크 텍스트
            links = page_state.get("links", [])
            if links:
                enhanced_auxiliary_data["links"] = links[:15]
            
            # 입력 필드 라벨
            input_labels = page_state.get("input_labels", [])
            if input_labels:
                enhanced_auxiliary_data["input_labels"] = input_labels[:10]
            
            # 주요 텍스트 콘텐츠 (요약)
            visible_text = page_state.get("visible_text", "")
            if visible_text:
                enhanced_auxiliary_data["visible_text"] = visible_text[:300]  # 최대 300자
        
        # 3. Moderation 검사 (정책 위반 가능성 확인)
        try:
            from utils.moderation_checker import check_update_run_memory_prompt
            url = enhanced_auxiliary_data.get("url")
            is_safe, moderation_result = check_update_run_memory_prompt(
                url=url,
                run_memory_content=run_memory_content
            )
            
            if not is_safe:
                logger.warning(f"Moderation 검사 실패: {moderation_result}")
                logger.warning("정책 위반 가능성으로 인해 LLM 호출을 건너뜁니다.")
                # 정책 위반 가능성이 있으면 기존 메모리 그대로 반환
                from repositories.ai_memory_repository import get_run_memory
                current_memory = get_run_memory(run_id)
                return (current_memory or {}, False)
        except ModerationError:
            # Moderation 검사 자체가 실패한 경우에도 계속 진행
            logger.warning("Moderation 검사 중 에러 발생 (계속 진행)", exc_info=True)
        except Exception as e:
            # 예상치 못한 에러도 로그만 남기고 계속 진행
            logger.warning(f"Moderation 검사 중 예상치 못한 에러 발생 (계속 진행): {e}", exc_info=True)
        
        # 4. Chain 실행 (이미지 없이 텍스트 정보만 사용)
        # # 이미지 사용 시 (주석 처리)
        # result = await run_chain(
        #     label="update-run-memory",
        #     image_base64=image_base64,
        #     auxiliary_data=enhanced_auxiliary_data,
        #     run_memory=run_memory_content,
        #     use_vision=True
        # )
        
        # 텍스트 정보만 사용 (일반 사용자 인지 가능한 정보)
        result = await run_chain(
            label="update-run-memory",
            image_base64=None,  # 이미지 사용 안 함
            auxiliary_data=enhanced_auxiliary_data,
            run_memory=run_memory_content,
            use_vision=False  # Vision 모델 사용 안 함
        )
        
        # 3. Chain 결과에서 content 추출
        updated_content = self._extract_content_from_result(result, run_memory_content)
        
        # 4. 수정사항 확인 (업데이트 전후 비교)
        has_changes = self._dicts_are_different(run_memory_content, updated_content)
        
        # 5. run_memory 실제 업데이트
        updated_memory = update_run_memory(run_id, updated_content)
        
        return (updated_memory, has_changes)

    async def filter_input_actions_with_run_memory(
        self,
        input_actions: List[Dict[str, Any]],
        run_id: UUID,
        from_node_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        입력 액션을 run_memory에 저장된 정보를 기반으로 필터링합니다.
        
        Args:
            input_actions: 입력값이 필요한 액션 리스트 (딕셔너리 형태)
            run_id: 탐색 세션 ID
            from_node_id: 시작 노드 ID
        
        Returns:
            처리 가능한 액션 리스트 (action_value가 채워진 딕셔너리 형태)
        """
        # 1. context 설정
        set_run_id(run_id)
        set_from_node_id(from_node_id)
        
        # 2. run_memory 조회
        run_memory_content = self._get_run_memory_content(run_id)
        
        # 3. chain에 input_actions와 run_memory 전달
        result = await run_chain(
            label="filter-action",
            input_actions=input_actions,
            run_memory=run_memory_content,
            use_vision=False
        )
        
        # 4. chain 결과에서 처리 가능한 액션 추출
        processable_actions = self._extract_actions_from_result(result)
        
        # 5. 처리 불가한 액션 식별 및 pending action에 삽입
        processable_action_keys = set()
        for action in processable_actions:
            key = self._create_action_key(action, include_selector=True)
            processable_action_keys.add(key)
        
        # input_actions 중 처리 불가한 액션 찾기
        for action in input_actions:
            # is_filled가 true인 액션은 무시
            if action.get("is_filled", False):
                continue
            
            action_key = self._create_action_key(action, include_selector=True)
            
            # 처리 가능한 액션에 포함되지 않은 경우 pending action에 삽입
            if action_key not in processable_action_keys:
                try:
                    pending_action_service = PendingActionService()
                    pending_action_service.create_pending_action(
                        run_id=run_id,
                        from_node_id=from_node_id,
                        action=action,
                        status="pending"
                    )
                except Exception as e:
                    # pending action 생성 실패는 로그만 남기고 계속 진행 (비치명적 에러)
                    logger.warning(f"pending action 생성 실패 (계속 진행): {e}", exc_info=True)
        
        # 6. 적절한 입력값이 있는 액션만 반환
        return processable_actions
    
    async def process_pending_actions_with_run_memory(
        self,
        run_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        pending actions를 run_memory에 저장된 정보를 기반으로 필터링하고,
        처리 가능한 액션은 삭제한 후 리스트를 반환합니다.
        
        Args:
            run_id: 탐색 세션 ID
        
        Returns:
            처리 가능한 액션 리스트 (action_value가 채워진 딕셔너리 형태)
        """
        # 1. run_memory 조회
        run_memory_content = self._get_run_memory_content(run_id)
        
        # 2. pending actions 조회
        pending_action_service = PendingActionService()
        pending_actions = pending_action_service.list_pending_actions(
            run_id=run_id,
            from_node_id=None,
            status="pending"
        )
        
        # 빈 pending actions인 경우 빈 리스트 반환
        if not pending_actions:
            return []
        
        # 3. pending actions를 filter-action 입력 형태로 변환
        pending_input_actions = []
        for pending in pending_actions:
            pending_dict = {
                "action_type": pending.get("action_type", ""),
                "action_target": pending.get("action_target", ""),
                "action_value": pending.get("action_value", ""),
                "selector": "",
                "role": "",
                "name": "",
                "tag": "",
                "href": "",
                "input_type": "",
                "placeholder": "",
                "input_required": True,
                "is_filled": False,
                "current_value": ""
            }
            pending_input_actions.append(pending_dict)
        
        # 4. chain에 pending_input_actions와 run_memory 전달
        result = await run_chain(
            label="process-pending-actions",
            input_actions=pending_input_actions,
            run_memory=run_memory_content,
            use_vision=False
        )
        
        # 5. chain 결과에서 처리 가능한 액션 추출
        processable_actions = self._extract_actions_from_result(result)
        
        # 6. 처리 가능한 액션에 해당하는 pending actions 삭제
        # 매칭 키: (action_type, action_target) 조합 사용
        # pending_action에는 selector/role/name이 없으므로 action_type + action_target으로 식별
        processable_action_keys = set()
        for action in processable_actions:
            key = self._create_action_key(action, include_selector=False)
            processable_action_keys.add(key)
        
        # pending actions 중 처리 가능한 것 삭제
        for pending in pending_actions:
            pending_key = self._create_action_key(pending, include_selector=False)
            
            # 처리 가능한 액션에 포함된 경우 pending action 삭제
            if pending_key in processable_action_keys:
                try:
                    pending_action_id = UUID(pending.get("id"))
                    delete_pending_action(pending_action_id)
                except Exception as e:
                    # pending action 삭제 실패는 로그만 남기고 계속 진행 (비치명적 에러)
                    logger.warning(f"pending action 삭제 실패 (계속 진행): {e}", exc_info=True)
        
        # 7. 처리 가능한 액션 리스트 반환
        return processable_actions
    
    async def guess_and_update_edge_intent(self, edge_id: UUID) -> str:
        """
        엣지의 의도를 추론하고 intent_label을 업데이트합니다.
        
        Args:
            edge_id: 엣지 ID
        
        Returns:
            업데이트된 intent_label 문자열
        
        Note:
            - from_node == to_node인 경우 스킵
            - LLM 응답이 15자를 초과하면 자동으로 잘라냄
        """
        try:
            # 1. 엣지 정보 조회
            edge = get_edge_by_id(edge_id)
            if not edge:
                raise EntityNotFoundError("엣지", entity_id=str(edge_id))
            
            from_node_id = edge.get("from_node_id")
            to_node_id = edge.get("to_node_id")
            
            # from_node == to_node인 경우 스킵
            if not from_node_id or not to_node_id or from_node_id == to_node_id:
                return ""
            
            # 2. 노드 정보 조회
            from_node = get_node_by_id(UUID(from_node_id))
            to_node = get_node_by_id(UUID(to_node_id))
            
            if not from_node:
                raise EntityNotFoundError("시작 노드", entity_id=str(from_node_id))
            if not to_node:
                raise EntityNotFoundError("도착 노드", entity_id=str(to_node_id))
            
            # 3. Chain 실행 (guess-intent)
            result = await run_chain(
                label="guess-intent",
                from_node=from_node,
                to_node=to_node,
                edge=edge,
                use_vision=False
            )
            
            # 4. Chain 결과에서 intent_label 추출
            intent_label = ""
            if isinstance(result, GuessIntentOutput):
                intent_label = result.intent_label
            elif isinstance(result, dict) and "intent_label" in result:
                intent_label = result["intent_label"]
            else:
                # 문자열로 반환된 경우
                intent_label = str(result).strip()
            
            # 5. 15자 초과 시 자동으로 잘라내기
            if len(intent_label) > 15:
                intent_label = intent_label[:15]
            
            # 6. 엣지 intent_label 업데이트
            if intent_label:
                update_edge_intent_label(edge_id, intent_label)
            
            return intent_label
            
        except (EntityNotFoundError, AIServiceError) as e:
            # 치명적 에러는 재발생하지 않고 로그만 남기고 빈 문자열 반환 (비치명적 처리)
            logger.warning(f"intent_label 생성 실패 (비치명적): {e.message}", exc_info=True)
            return ""
        except Exception as e:
            # 예상치 못한 에러도 로그만 남기고 빈 문자열 반환
            logger.error(f"intent_label 생성 중 예상치 못한 에러 발생: {e}", exc_info=True)
            return ""