"""label → PydanticOutputParser 매핑. Chain 출력 파싱용."""
from langchain.output_parsers import PydanticOutputParser
from schemas.filter_action import FilterActionOutput
from schemas.run_memory import UpdateRunMemoryOutput
from schemas.guess_intent import GuessIntentOutput

# label → PydanticOutputParser
parser_map = {
    "filter-action": PydanticOutputParser(pydantic_object=FilterActionOutput),
    "process-pending-actions": PydanticOutputParser(pydantic_object=FilterActionOutput),
    "update-run-memory": PydanticOutputParser(pydantic_object=UpdateRunMemoryOutput),
    "guess-intent": PydanticOutputParser(pydantic_object=GuessIntentOutput),
}

def get_parser(label: str) -> PydanticOutputParser | None:
    """레이블에 해당하는 파서를 반환합니다. 없으면 None을 반환합니다."""
    return parser_map.get(label)