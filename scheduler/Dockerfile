FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY model.py .
COPY data/ data/
COPY app.py .
COPY demo_job_batch.json .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]