"""SolTranNet Aqueous-Solubility MCP Server — logS prediction.

Provides an ``execute_soltrannet_code`` MCP tool plus a ``predict_solubility``
domain tool, backed by the open-source `SolTranNet
<https://github.com/gnina/SolTranNet>`_ aqueous-solubility model loaded
**in-kernel**. It predicts ``logS`` (log10 of aqueous solubility in mol/L).

The inference stack (``soltrannet``, ``torch``, ``rdkit``, ``numpy``) is
installed into the conda kernel at build time (see ``ENVIRONMENT_YML`` /
``additional_commands``). SolTranNet's trained weights ship inside its pip
package, so — unlike the redox / retrosynthesis servers — there is no external
checkpoint to fetch or bake. Inference runs on CPU out of the box.

Usage:
    python -m servers.soltrannet.server.soltrannet_server
"""

import asyncio
import os
import sys
from pathlib import Path

from agora_workbench.code_execution import CodeExecutionServer, ServerConfig, Skill, State, ToolRegistry
from agora_workbench.code_execution.auth import create_noop_auth_config
from agora_workbench.code_execution.data_access import AssetPublisher, BlobPublisher, LocalFilePublisher
from agora_workbench.code_execution.data_access.credentials import create_storage_credential

from servers.peers import peer_registry_for
from servers.soltrannet.states import STATE_AFFORDANCES, SoltrannetState
from servers.soltrannet.tools import SOLTRANNET_TOOLS

_SOLTRANNET_TOOLS_PKG = str(Path(__file__).resolve().parent.parent / "soltrannet_tools")
_ENVIRONMENT_FILE = Path(__file__).resolve().parent.parent / "environment.yml"
_SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "SKILL.md"

SOLTRANNET_SKILLS = [
    Skill(
        name="soltrannet-solubility",
        description=(
            "Predict aqueous solubility (logS) for organic redox-flow-battery "
            "candidate molecules using the open-source SolTranNet model (trained "
            "on AqSolDB), via the predict_solubility tool and the "
            "execute_soltrannet_code tool."
        ),
        domain="soltrannet",
        states=[state.value for state in SoltrannetState],
        content=_SKILL_PATH.read_text(encoding="utf-8"),
        path=str(_SKILL_PATH),
    ),
]

SOLTRANNET_STATES = [
    State(state.value, description=state.name.replace("_", " ").title(), affordances=STATE_AFFORDANCES[state])
    for state in SoltrannetState
]

# SolTranNet solubility environment (see environment.yml). The interpreter,
# Agora kernel bits, numpy and rdkit come from conda; soltrannet + a CPU torch
# build are pip-installed in additional_commands below.
ENVIRONMENT_YML = _ENVIRONMENT_FILE.read_text(encoding="utf-8")

config = ServerConfig(
    name="soltrannet",
    description=(
        "Execute Python code to predict the aqueous solubility (logS, log10 of "
        "solubility in mol/L) of organic redox-flow-battery candidate molecules "
        "with the open-source SolTranNet model. Domain tool: predict_solubility."
    ),
    type="conda",
    dependency_file=ENVIRONMENT_YML,
    auto_build=True,
    additional_commands=[
        # CPU build of torch (keeps the image lean and avoids pulling CUDA).
        "python -m pip install torch --index-url https://download.pytorch.org/whl/cpu",
        # SolTranNet itself. Installed with --no-deps so pip does NOT pull the
        # PyPI ``pathlib`` backport (which shadows and breaks the stdlib module on
        # modern Python); torch is installed above and rdkit/numpy come from conda.
        "python -m pip install --no-deps soltrannet",
        # In-kernel SolTranNet tools (declares no runtime deps).
        f"python -m pip install --no-deps {_SOLTRANNET_TOOLS_PKG}",
    ],
    peer_registry=peer_registry_for("soltrannet"),
)


class SoltrannetServer(CodeExecutionServer):
    """SolTranNet-specific MCP server for aqueous-solubility (logS) prediction."""


tool_registry = ToolRegistry(package="soltrannet_tools")
for tool_def in SOLTRANNET_TOOLS:
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

server = SoltrannetServer(
    server_config=config,
    tool_registry=tool_registry,
    auth_config=create_noop_auth_config(),
    publishers=_publishers,
    skills=SOLTRANNET_SKILLS,
    states=SOLTRANNET_STATES,
)

if __name__ == "__main__":
    if "--warm" in sys.argv:
        asyncio.run(server.warm())
    else:
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        asyncio.run(server.run_http(host=host, port=port))
