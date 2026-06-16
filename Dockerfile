# Imagem enxuta para a interface web do HirePilot.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    SEARCH_SOURCES=gupy,remotive,remoteok \
    USE_SEMANTIC_MATCHING=false

WORKDIR /app

# Instala dependências primeiro para aproveitar o cache de camadas
COPY requirements-web.txt ./
RUN pip install -r requirements-web.txt

# Copia o código e instala o pacote (sem dependências, já instaladas acima)
COPY . .
RUN pip install --no-deps -e .

RUN mkdir -p /app/data && useradd -m app && chown -R app /app
USER app

EXPOSE 5000

# 1 worker para manter o estado de sessão (in-memory) consistente; threads p/ concorrência
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-w", "1", "--threads", "8", \
     "--timeout", "180", "cv_apply.webapp:app"]
