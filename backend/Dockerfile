FROM python:3.13.18-slim-trixie

# Sin archivos de caché de Python en la imagen ni al ejecutarla
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

COPY . .

# /datos ya tiene dueño al crear el volumen, para que el usuario app pueda escribir la base
RUN useradd --system --no-create-home app && mkdir /datos && chown app:app /datos
USER app

EXPOSE 8001
# exec deja a uvicorn como proceso principal, para que reciba la señal de parada
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port 8001"]
