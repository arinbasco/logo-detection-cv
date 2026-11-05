FROM python:3.13.18-slim-trixie

# Sin archivos de caché de Python en la imagen ni al ejecutarla
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY main.py best.onnx ./

RUN useradd --system --no-create-home app
USER app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
