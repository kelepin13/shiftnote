# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --create-home --uid 10001 app

# Dependencies first so code changes don't reinstall them.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY evals ./evals
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Provider and key come from the environment, e.g.
#   docker run -p 8000:8000 -e SHIFTNOTE_PROVIDER=openai -e SHIFTNOTE_API_KEY=sk-... shiftnote
CMD ["uvicorn", "shiftnote.api:app", "--host", "0.0.0.0", "--port", "8000"]
