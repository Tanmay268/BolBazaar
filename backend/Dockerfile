FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md* ./
COPY src ./src
RUN pip install .

# Render injects PORT; the app reads PORT and HOST from the environment.
EXPOSE 8000
CMD ["bolbazaar-api"]
