FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd -m -u 1000 judge
USER judge
ENTRYPOINT ["python", "-m", "llm_judge", "run"]
