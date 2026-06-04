FROM python:3.12-slim

WORKDIR /app

# Timezone
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY --chown=root:root . .

# Build CSS
RUN python build_css.py && rm build_css.py

# Data directory (only writable path)
RUN mkdir -p /app/data && chown appuser:appuser /app/data

# Drop root
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/prefix')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
