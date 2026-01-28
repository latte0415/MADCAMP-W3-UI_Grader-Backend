# Python 3.11 베이스 이미지 사용
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 Playwright 브라우저 설치에 필요한 의존성 설치
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt 복사 및 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright 브라우저 설치
RUN playwright install chromium
RUN playwright install-deps chromium

# 애플리케이션 코드 복사
COPY . .

# Railway는 PORT 환경 변수를 자동으로 제공합니다
# 기본값으로 8000 포트 사용
ENV PORT=8000

# 헬스체크용 포트 노출
EXPOSE $PORT

# 기본 명령어 (Procfile이나 railway.json에서 오버라이드 가능)
# Railway는 PORT 환경 변수를 자동으로 제공하므로 쉘을 통해 사용
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
