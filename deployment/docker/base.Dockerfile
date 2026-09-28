# Base image for ORFB Design MCP servers.
#
# Installs the published agora-workbench release from PyPI; no source checkout
# is required in the build context.

ARG AGORA_WORKBENCH_VERSION=0.3.1

FROM mcr.microsoft.com/azurelinux/base/python:3.12

WORKDIR /app

RUN tdnf install -y shadow-utils && tdnf clean all && \
    useradd -m -d /home/appuser -s /bin/bash appuser

RUN tdnf install -y \
    ca-certificates \
    bash \
    curl \
    git \
    tar \
    gzip \
    bzip2 \
    xz \
    gawk \
    && tdnf clean all

ARG UV_VERSION=0.12.2
RUN python3 -m pip install --no-cache-dir --root-user-action=ignore "uv==${UV_VERSION}"

ARG MINIFORGE_VERSION=25.11.0-1
RUN curl -L -O "https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-Linux-x86_64.sh" && \
    bash Miniforge3-Linux-x86_64.sh -b -p /opt/miniforge3 && \
    rm Miniforge3-Linux-x86_64.sh && \
    chown -R appuser:appuser /opt/miniforge3
ENV PATH="/opt/miniforge3/bin:$PATH"

RUN python3 -m pip install --upgrade pip

RUN mkdir -p /opt/wheelhouse && \
    python3 -m pip download --dest /opt/wheelhouse "ipykernel>=6.29.0" && \
    chown -R appuser:appuser /opt/wheelhouse

ARG AGORA_WORKBENCH_VERSION
RUN python3 -m pip install --no-input \
    "agora-workbench[azure,catalog-vector]==${AGORA_WORKBENCH_VERSION}"

RUN mkdir -p /home/appuser/.cache/mcp-envs && \
    chown -R appuser:appuser /app /home/appuser

ENV PYTHONPATH="/app"
ENV HOME=/home/appuser

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
