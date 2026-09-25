# gcc:13 — matches the version committed to in the D0 proposal. The official
# image already ships g++/gcc, so no separate build-essential install is needed.
FROM gcc:13

# Create a non-root user for security
RUN useradd -m runner
USER runner
WORKDIR /workspace
