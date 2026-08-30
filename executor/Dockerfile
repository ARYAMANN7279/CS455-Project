# Minimal Python sandbox — one container per code run, destroyed after execution
FROM python:3.12-slim

# No network, no extra packages, minimal surface
RUN useradd -m -u 1000 sandbox

WORKDIR /sandbox
USER sandbox

# Entrypoint: receives code on stdin, runs it with limits enforced by the caller
ENTRYPOINT ["python3", "-c"]
