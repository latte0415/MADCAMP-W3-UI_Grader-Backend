"""label → PydanticOutputParser 매핑. Chain 출력 파싱용."""
from langchain.output_parsers import PydanticOutputParser
from schemas.filter_action import FilterActionOutput

# label → PydanticOutputParser
parser_map = {
    "filter-action": PydanticOutputParser(pydantic_object=FilterActionOutput),
}

def get_parser(label: str) -> PydanticOutputParser | None:
    """레이블에 해당하는 파서를 반환합니다. 없으면 None을 반환합니다."""
    return parser_map.get(label)