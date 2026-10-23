# Base image for ORFB Design MCP servers.
#
# Installs the published agora-workbench release from PyPI; no source checkout
# is required in the build context.

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
ARG MINIFORGE_SHA256=be1bad9d4e67a8753eb76fb4940e9a08036786675c7adf060627e55791bf110d
RUN curl -fL -o /tmp/miniforge.sh \
      "https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-Linux-x86_64.sh" && \
    echo "${MINIFORGE_SHA256}  /tmp/miniforge.sh" | sha256sum -c - && \
    bash /tmp/miniforge.sh -b -p /opt/miniforge3 && \
    rm /tmp/miniforge.sh && \
    chown -R appuser:appuser /opt/miniforge3
ENV PATH="/opt/miniforge3/bin:$PATH"

# Pre-download the hash-locked Jupyter kernel stack used when Agora builds
# isolated execution environments.
COPY deployment/docker/ipykernel-requirements.txt /tmp/ipykernel-requirements.txt
RUN mkdir -p /opt/wheelhouse && \
    python3 -m pip download --require-hashes \
      --dest /opt/wheelhouse \
      -r /tmp/ipykernel-requirements.txt && \
    rm /tmp/ipykernel-requirements.txt && \
    chown -R appuser:appuser /opt/wheelhouse

# Export the runtime dependency graph from the committed uv lock, then enforce
# every artifact hash while installing it into the Miniforge base environment.
COPY pyproject.toml uv.lock /tmp/orfb-lock/
RUN cd /tmp/orfb-lock && \
    uv export --frozen --no-dev --no-editable --no-emit-project \
      --format requirements-txt --output-file requirements.txt && \
    uv pip install --python /opt/miniforge3/bin/python \
      --require-hashes -r requirements.txt && \
    rm -rf /tmp/orfb-lock

RUN mkdir -p /home/appuser/.cache/mcp-envs && \
    chown -R appuser:appuser /app /home/appuser

ENV PYTHONPATH="/app"
ENV HOME=/home/appuser

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
