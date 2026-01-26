import sys
import asyncio
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from services.ai_service import AiService

async def test_ai_skeleton() -> None:
    ai_service = AiService()
    response = await ai_service.get_ai_response()
    print(response)

    response = await ai_service.get_ai_response_with_calculator_tools()
    print(response)

if __name__ == "__main__": 
    try:
        asyncio.run(test_ai_skeleton())
        print("✓ ai_skeleton 테스트 통과")
    except Exception as e:
        print(f"✗ ai_skeleton 테스트 실패: {e}")
        sys.exit(1)