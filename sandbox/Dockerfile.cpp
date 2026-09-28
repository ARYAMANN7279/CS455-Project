# D0 proposal commits to gcc:13 as the C++ sandbox base image.
FROM gcc:13

# Create a non-root user for security
# Fixed uid, see SANDBOX_UID in backend/app/services/sandbox.py
RUN useradd -m --uid 10001 runner
USER runner
WORKDIR /workspace
