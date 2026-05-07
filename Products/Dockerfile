FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY unified_Products.py ./
COPY templates ./templates
COPY API_USAGE.md ./API_USAGE.md

EXPOSE 5000

ENV FLASK_APP=unified_Products.py
ENV DYNAMODB_TABLE=onlineStore
ENV ENABLE_XRAY=TRUE
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
