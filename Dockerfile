FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Seoul

WORKDIR /app

# 의존성 레이어를 먼저 캐싱
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dcbot ./dcbot
COPY main.py .

# 상태 파일 저장 위치 (Cloud Run 등에서는 볼륨/GCS 사용 권장)
RUN mkdir -p /app/state
VOLUME ["/app/state"]

# 루트가 아닌 사용자로 실행
RUN useradd --create-home --uid 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Cloud Run 등에서 PORT 를 주입하면 헬스체크 서버가 열린다.
EXPOSE 8080

CMD ["python", "main.py"]
