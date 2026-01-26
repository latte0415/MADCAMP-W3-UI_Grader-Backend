import os
from langchain_core.callbacks import StdOutCallbackHandler
from langchain_core.globals import set_verbose
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LANGCHAIN_TRACING = os.getenv("LANGCHAIN_TRACING", "false").lower() == "true"
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY")

# LangSmith 트레이싱은 API 키가 있을 때만 활성화
if LANGCHAIN_TRACING and LANGCHAIN_API_KEY:
    set_verbose(True)
elif LANGCHAIN_TRACING and not LANGCHAIN_API_KEY:
    print("Warning: LANGCHAIN_TRACING is enabled but LANGCHAIN_API_KEY is not set. Tracing will be disabled.")
    # 트레이싱 비활성화
    os.environ["LANGCHAIN_TRACING"] = "false"
else:
    # 명시적으로 트레이싱 비활성화
    os.environ["LANGCHAIN_TRACING"] = "false"

callback_handler = StdOutCallbackHandler()

def get_llm(model: str = "gpt-4o-mini"):
    """
    LLM 인스턴스를 반환합니다.
    
    Args:
        model: 사용할 모델명 (기본값: "gpt-4o-mini")
              Vision이 필요한 경우 "gpt-4o" 사용
    
    Returns:
        ChatOpenAI 인스턴스
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    llm = ChatOpenAI(
        model=model,
        temperature=0.5,
        max_tokens=1024,
        timeout=30,
        max_retries=3,
        callbacks=[callback_handler],
    )
    return llm