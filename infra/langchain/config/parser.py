"""label → PydanticOutputParser 매핑. 에이전트 출력 파싱용."""
from langchain.output_parsers import PydanticOutputParser

# label → PydanticOutputParser (현재 비어 있음, 확장 시 사용)
parser_map = {}

def get_parser(label: str) -> PydanticOutputParser | None:
    """레이블에 해당하는 파서를 반환합니다. 없으면 None을 반환합니다."""
    return parser_map.get(label)