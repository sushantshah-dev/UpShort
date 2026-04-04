FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    "flask>=3.1" \
    "peewee>=3.17" \
    "psycopg2-binary>=2.9" \
    "python-dotenv>=1.0" \
    "redis>=5.2"

COPY . /app

EXPOSE 5000

CMD ["python", "run.py"]
