FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code & model data
COPY app.py ml_engine.py Data_Finance_6_Bulan.csv ./
COPY tests/ ./tests/

# Hugging Face Space runs on port 7860
EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
