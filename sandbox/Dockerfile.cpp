# Use a lightweight base image
FROM ubuntu:22.04

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install build-essential (g++, make, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    g++ \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd -m runner
USER runner
WORKDIR /workspace
