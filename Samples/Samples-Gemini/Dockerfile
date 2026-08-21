# Step 6.5 -- containerising the Gemini agent service.
#
# Same reasoning as ../Samples/Dockerfile: "it runs on my machine" is not a
# deployment, and a container is the smallest artifact that makes the
# service reproducible.
#
# Build:  docker build -t dorm-agent-gemini Samples-Gemini/
# Run:    docker run --rm -p 8000:8000 \
#             -e GEMINI_API_KEY=... \
#             -e API_KEYS=dev-key-123 \
#             dorm-agent-gemini
# Check:  curl -s localhost:8000/health

FROM python:3.12-slim

# uv, the same tool you use locally -- copied in from Astral's published image
# so the container builds the same way your laptop does.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_SYSTEM_PYTHON=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependencies first, in their own layer: they change far less often than your
# code, so Docker can reuse this layer on every subsequent build. Pinning
# minimums (not exact versions) keeps the sample from rotting; a real service
# would copy a uv.lock instead and get an exact, reproducible install.
RUN uv pip install --system --no-cache \
        "google-genai>=1.0" \
        "fastapi>=0.110" \
        "uvicorn[standard]>=0.30" \
        "pydantic>=2.6"

# Only the files the service actually needs -- not the whole learning repo.
# A smaller image has a smaller attack surface, and copying less means fewer
# accidental secrets baked into a layer forever.
COPY config.py step3_agent.py step6_service.py ./

# 6.4 LEAST PRIVILEGE: containers run as root unless you say otherwise. An
# agent executes model-chosen actions, so "root inside the container" is a
# meaningfully worse starting position than it is for a plain web app.
RUN useradd --system --uid 10001 appuser
USER appuser

EXPOSE 8000

# `python:*-slim` has no curl, so probe with the stdlib.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health')"

# No --reload in a container: it watches the filesystem, doubles memory, and
# there is nothing to reload from. That flag is for your laptop only.
CMD ["uvicorn", "step6_service:app", "--host", "0.0.0.0", "--port", "8000"]
