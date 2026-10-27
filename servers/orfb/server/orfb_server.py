# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""ORFB Design MCP Server — RDKit molecule characterization.

Provides an ``execute_orfb_code`` MCP tool backed by a conda environment with
RDKit and common scientific Python packages. This is the user-facing
characterization server in the ORFB design network; it offers the lightweight
RDKit tools:

  * molecular properties    — RDKit physicochemical descriptors
  * tanimoto_similarity     — Morgan-fingerprint similarity to a target
  * sa_score                — synthetic accessibility score

Redox potential prediction and retrosynthesis are heavyweight ML models served
by dedicated peer servers (``graphormer`` and ``retrochimera``), composed with
this server behind the ``orfb-hub`` RouterServer. Molecules can be pushed to a
peer kernel with ``orfb_send(to="graphormer")`` / ``orfb_send(to="retrochimera")``.

Domain-specific tool implementations live in the ``orfb_tools`` pip package
(under ``orfb_tools/``), installed into the conda environment via
``additional_commands``. The server holds only the ``ToolDefinition`` metadata;
the kernel imports implementations from the installed package.

Usage:
    python -m servers.orfb.server.orfb_server

Requires the agora-workbench base image (mcp-server-base:local) when run in
Docker. See the README for full instructions.
"""

import asyncio
import os
import sys
from pathlib import Path

from agora_workbench.code_execution import CodeExecutionServer, ServerConfig, Skill, State, ToolRegistry
from agora_workbench.code_execution.auth import create_noop_auth_config
from agora_workbench.code_execution.data_access import AssetPublisher, BlobPublisher, LocalFilePublisher
from agora_workbench.code_execution.data_access.credentials import create_storage_credential

from servers.orfb.states import STATE_AFFORDANCES, OrfbState
from servers.orfb.tools import ORFB_TOOLS
from servers.peers import peer_registry_for

# Path to the orfb_tools package (relative to this file so it works both inside
# Docker and when running locally from the repo root).
_ORFB_TOOLS_PKG = str(Path(__file__).resolve().parent.parent / "orfb_tools")
_PROVENANCE_PKG = str(Path(__file__).resolve().parents[2] / "provenance_tools")
_SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "SKILL.md"

# ---------------------------------------------------------------------------
# Skills — explicit definition with content loaded from the markdown file.
# ---------------------------------------------------------------------------

ORFB_SKILLS = [
    Skill(
        name="orfb-design",
        description=(
            "Organic redox-flow-battery (ORFB) molecule design — characterize "
            "candidate molecules with RDKit descriptors, predict reduction and "
            "oxidation potentials, score similarity to a target and synthetic "
            "accessibility, and predict retrosynthetic routes, via domain tools "
            "and the execute_orfb_code tool."
        ),
        domain="orfb",
        states=[state.value for state in OrfbState],
        content=_SKILL_PATH.read_text(encoding="utf-8"),
        path=str(_SKILL_PATH),
    ),
]

ORFB_STATES = [
    State(state.value, description=state.name.replace("_", " ").title(), affordances=STATE_AFFORDANCES[state])
    for state in OrfbState
]

ENVIRONMENT_YML = """\
name: orfb
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - rdkit
  - numpy
  - pandas
  - scipy
"""

RDKIT_PRELUDE = """\
from rdkit import Chem
from rdkit.Chem import Draw, Descriptors, AllChem, rdMolDescriptors
from rdkit.Chem import PandasTools
import numpy as np
import pandas as pd
"""

config = ServerConfig(
    name="orfb",
    description=(
        "Execute Python code for organic redox-flow-battery (ORFB) molecule "
        "characterization with RDKit. Available libraries: RDKit, numpy, pandas, "
        "scipy. Domain tools cover molecular descriptors, Tanimoto similarity and "
        "synthetic accessibility scoring. Redox potential prediction and "
        "retrosynthesis are served by the graphormer and retrochimera peers."
    ),
    type="conda",
    dependency_file=ENVIRONMENT_YML,
    auto_build=True,
    additional_commands=[
        f"python -m pip install --no-deps {_PROVENANCE_PKG}",
        # Install the orfb_tools package into the conda environment so that tool
        # proxy imports (e.g. ``from orfb_tools.sa_score import sa_score``)
        # resolve correctly inside the kernel.
        f"python -m pip install --no-deps {_ORFB_TOOLS_PKG}",
    ],
    # Peer servers reachable via orfb_send(to=...). Override per-deployment with
    # the AGORA_PEER_REGISTRY env var. See servers/peers.py.
    peer_registry=peer_registry_for("orfb"),
)


class OrfbServer(CodeExecutionServer):
    """ORFB-specific MCP server with auto-imported RDKit modules."""

    def preprocess_code(self, code: str) -> str:
        """Inject common RDKit imports before user code."""
        return RDKIT_PRELUDE + code


# Build the tool registry from domain tool definitions. The package default is
# only a fallback — every ORFB tool sets an explicit ``module``.
tool_registry = ToolRegistry(package="orfb_tools")
for tool_def in ORFB_TOOLS:
    tool_registry.register_tool(tool_def)

# Configure publishers so the publish_artifact tool is available.
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

server = OrfbServer(
    server_config=config,
    tool_registry=tool_registry,
    auth_config=create_noop_auth_config(),
    publishers=_publishers,
    skills=ORFB_SKILLS,
    states=ORFB_STATES,
)

if __name__ == "__main__":
    if "--warm" in sys.argv:
        asyncio.run(server.warm())
    else:
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        asyncio.run(server.run_http(host=host, port=port))
