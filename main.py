"""FastAPI 앱 엔트리포인트. health check 엔드포인트 제공."""
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def health_check():
    """헬스 체크. Returns: {"status": "ok"}"""
    return {"status": "ok"}