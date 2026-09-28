"""Graphormer Redox MCP Server — reduction / oxidation potential prediction.

Provides an ``execute_graphormer_code`` MCP tool plus ``predict_reduction_
potential`` / ``predict_oxidation_potential`` domain tools, backed by the
Graphormer redox model. The checkpoints are loaded **once per container** by a
co-located sidecar (``graphormer_tools.model_service``, declared via
``SidecarConfig`` below) and served over loopback HTTP, rather than being
reloaded inside every isolated kernel session — keeping the pattern uniform with
the retrochimera server.

The heavyweight inference stack is built from a pinned public
``microsoft/Graphormer`` checkout and its pinned Fairseq submodule.
``GRAPHORMER_CHECKPOINT_DIR`` points at the redox checkpoints baked into the
server image.

Usage:
    python -m servers.graphormer.server.graphormer_server
"""

import asyncio
import os
import sys
from pathlib import Path

from agora_workbench.code_execution import (
    CodeExecutionServer,
    ServerConfig,
    SidecarConfig,
    Skill,
    State,
    ToolRegistry,
)
from agora_workbench.code_execution.auth import create_noop_auth_config
from agora_workbench.code_execution.data_access import AssetPublisher, BlobPublisher, LocalFilePublisher
from agora_workbench.code_execution.data_access.credentials import create_storage_credential

from servers.graphormer.states import STATE_AFFORDANCES, GraphormerState
from servers.graphormer.tools import GRAPHORMER_TOOLS
from servers.peers import peer_registry_for

_SERVER_PKG_DIR = Path(__file__).resolve().parent.parent
_GRAPHORMER_TOOLS_PKG = str(_SERVER_PKG_DIR / "graphormer_tools")
_GRAPHORMER_SOURCE_DIR = os.getenv("GRAPHORMER_SOURCE_DIR", "/app/graphormer-source")
_ENVIRONMENT_FILE = _SERVER_PKG_DIR / "environment-graphormer.yml"
_SKILL_PATH = _SERVER_PKG_DIR / "skills" / "SKILL.md"

GRAPHORMER_SKILLS = [
    Skill(
        name="graphormer-redox",
        description=(
            "Predict reduction and oxidation potentials (volts versus SHE) for "
            "organic redox-flow-battery candidate molecules using the Graphormer "
            "redox model, via the predict_reduction_potential / "
            "predict_oxidation_potential tools and the execute_graphormer_code tool."
        ),
        domain="graphormer",
        states=[state.value for state in GraphormerState],
        content=_SKILL_PATH.read_text(encoding="utf-8"),
        path=str(_SKILL_PATH),
    ),
]

GRAPHORMER_STATES = [
    State(state.value, description=state.name.replace("_", " ").title(), affordances=STATE_AFFORDANCES[state])
    for state in GraphormerState
]

# Compatibility environment for the pinned public Graphormer revision:
# Python 3.9, torch 1.9.1+cu111, OGB and torch-geometric, plus the toolchain
# needed to compile Fairseq and Graphormer's Cython ``algos`` extension.
ENVIRONMENT_YML = _ENVIRONMENT_FILE.read_text(encoding="utf-8")

config = ServerConfig(
    name="graphormer",
    description=(
        "Execute Python code to predict organic redox-flow-battery redox "
        "potentials with the Graphormer model. Domain tools: "
        "predict_reduction_potential and predict_oxidation_potential (volts vs "
        "SHE)."
    ),
    type="conda",
    dependency_file=ENVIRONMENT_YML,
    auto_build=True,
    additional_commands=[
        # Expose unprefixed C/C++ compilers (conda-forge ships only the
        # ``x86_64-conda-linux-gnu-*`` names) and a ``which`` shim (absent on
        # the minimal Azure Linux base) so torch/distutils source builds work.
        (
            'ln -sf x86_64-conda-linux-gnu-gcc "$CONDA_PREFIX/bin/gcc" && '
            'ln -sf x86_64-conda-linux-gnu-g++ "$CONDA_PREFIX/bin/g++" && '
            'ln -sf x86_64-conda-linux-gnu-c++ "$CONDA_PREFIX/bin/c++" && '
            'ln -sf x86_64-conda-linux-gnu-cc "$CONDA_PREFIX/bin/cc" && '
            'printf \'#!/usr/bin/env bash\\ncommand -v "$@"\\n\' > "$CONDA_PREFIX/bin/which" && '
            'chmod +x "$CONDA_PREFIX/bin/which"'
        ),
        f'test -f "{_GRAPHORMER_SOURCE_DIR}/fairseq/setup.py"',
        # Install the exact Fairseq submodule pinned by Microsoft Graphormer.
        (
            f'cd "{_GRAPHORMER_SOURCE_DIR}/fairseq" && '
            'CFLAGS="-include cstdint" CXXFLAGS="-include cstdint" '
            "CC=gcc CXX=g++ python -m pip install --no-deps --no-build-isolation ."
        ),
        # Expose the source checkout in the conda env and compile the shortest
        # path extension in place; Graphormer intentionally has no package
        # metadata of its own.
        (
            "python -c 'from pathlib import Path; import site; "
            f'Path(site.getsitepackages()[0], "graphormer-source.pth").write_text("{_GRAPHORMER_SOURCE_DIR}\\n")\''
        ),
        (
            f'cd "{_GRAPHORMER_SOURCE_DIR}" && python -c \'import numpy, pyximport; '
            'pyximport.install(setup_args={"include_dirs": numpy.get_include()}, '
            "inplace=True, language_level=3); import graphormer.data.algos'"
        ),
        # In-kernel Graphormer tools (build isolation -> modern setuptools for
        # the PEP 621 metadata; the env's pinned setuptools 59.5.0 is too old).
        f"python -m pip install --no-deps {_GRAPHORMER_TOOLS_PKG}",
    ],
    # Load the redox checkpoints ONCE per container in a co-located sidecar
    # instead of inside every isolated kernel session, keeping the pattern
    # uniform with retrochimera. Kernels reach it over loopback via
    # GRAPHORMER_MODEL_SERVICE_URL. The sidecar runs in this server's kernel
    # environment (use_env_python) so it shares the model stack, and inherits
    # GRAPHORMER_CHECKPOINT_DIR / GRAPHORMER_DEVICE from the container.
    sidecars=[
        SidecarConfig(
            name="graphormer-model",
            command=["-m", "graphormer_tools.model_service"],
            url_env_var="GRAPHORMER_MODEL_SERVICE_URL",
            port=8902,
            health_path="/health",
            readiness_timeout_s=300.0,
        ),
    ],
    peer_registry=peer_registry_for("graphormer"),
)


class GraphormerServer(CodeExecutionServer):
    """Graphormer-specific MCP server for redox potential prediction."""


tool_registry = ToolRegistry(package="graphormer_tools")
for tool_def in GRAPHORMER_TOOLS:
    tool_registry.register_tool(tool_def)

_PUBLISH_DIR = Path(os.getenv("PUBLISH_DIR", "/tmp/published_artifacts"))
_publishers: list[AssetPublisher] = [LocalFilePublisher(base_dir=_PUBLISH_DIR)]

_blob_account_url = os.getenv("BLOB_PUBLISH_ACCOUNT_URL")
_blob_container = os.getenv("BLOB_PUBLISH_CONTAINER", "artifacts")
if _blob_account_url:
    _publishers.append(
        BlobPublisher(
            account_url=_blob_account_url,
            container=_blob_container,
            credential=create_storage_credential(),
        )
    )

server = GraphormerServer(
    server_config=config,
    tool_registry=tool_registry,
    auth_config=create_noop_auth_config(),
    publishers=_publishers,
    skills=GRAPHORMER_SKILLS,
    states=GRAPHORMER_STATES,
)

if __name__ == "__main__":
    if "--warm" in sys.argv:
        asyncio.run(server.warm())
    else:
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        asyncio.run(server.run_http(host=host, port=port))
