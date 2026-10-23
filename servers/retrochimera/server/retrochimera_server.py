"""RetroChimera Retrosynthesis MCP Server — route prediction.

Provides an ``execute_retrochimera_code`` MCP tool plus a
``predict_retrosynthesis`` domain tool, backed by the RetroChimera single-step
model with RetroStar multi-step search. The heavy planning model is loaded
**once per container** by a co-located sidecar (``retrochimera_tools.model_service``,
declared via ``SidecarConfig`` below) and served over loopback HTTP, rather than
being reloaded inside every isolated kernel session (which OOM-killed the host).

The planning stack (``retrochimera``, ``syntheseus``, ``torch``, ``rdkit``, ...)
is pip-installed into the conda kernel at build time (see ``ENVIRONMENT_YML`` /
``additional_commands``); the Pistachio checkpoint is baked into the image and
pointed to by ``RETROCHIMERA_CHECKPOINT_DIR``. Inference runs on CPU out of the
box.

Usage:
    python -m servers.retrochimera.server.retrochimera_server
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

from servers.peers import peer_registry_for
from servers.retrochimera.states import STATE_AFFORDANCES, RetrochimeraState
from servers.retrochimera.tools import RETROCHIMERA_TOOLS

_RETRO_TOOLS_PKG = str(Path(__file__).resolve().parent.parent / "retrochimera_tools")
_PROVENANCE_PKG = str(Path(__file__).resolve().parents[2] / "provenance_tools")
_ENVIRONMENT_FILE = Path(__file__).resolve().parent.parent / "environment.yml"
_REQUIREMENTS_FILE = Path(__file__).resolve().parent.parent / "requirements.txt"
_SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "SKILL.md"

RETROCHIMERA_SKILLS = [
    Skill(
        name="retrochimera-retrosynthesis",
        description=(
            "Plan retrosynthetic routes for organic redox-flow-battery candidate "
            "molecules using the RetroChimera model with RetroStar multi-step "
            "search and a user-supplied purchasable-compound inventory, via the "
            "predict_retrosynthesis tool and the execute_retrochimera_code tool."
        ),
        domain="retrochimera",
        states=[state.value for state in RetrochimeraState],
        content=_SKILL_PATH.read_text(encoding="utf-8"),
        path=str(_SKILL_PATH),
    ),
]

RETROCHIMERA_STATES = [
    State(state.value, description=state.name.replace("_", " ").title(), affordances=STATE_AFFORDANCES[state])
    for state in RetrochimeraState
]

# RetroChimera planning environment (see environment.yml). The interpreter +
# Agora kernel bits come from conda; the heavy planning stack is pip-installed
# in additional_commands below.
ENVIRONMENT_YML = _ENVIRONMENT_FILE.read_text(encoding="utf-8")

config = ServerConfig(
    name="retrochimera",
    description=(
        "Execute Python code to plan retrosynthetic routes for organic "
        "redox-flow-battery candidate molecules with the RetroChimera model. "
        "Domain tool: predict_retrosynthesis."
    ),
    # RetroStar planning is CPU-intensive and can take tens of minutes for one
    # target — far longer than a synchronous MCP/proxy request timeout. Run in
    # ``adaptive`` mode:
    # every ``execute_retrochimera_code`` call starts synchronously but, if it is
    # still running after ``promotion_threshold_s``, it is automatically promoted
    # to a background job and returns a job handle the agent polls with
    # ``retrochimera_check_job``. The threshold (45s) is kept safely under the
    # hub proxy's client timeout so promotion happens before the proxy call could
    # time out. Fast follow-ups (e.g. inspecting a prior result) still return
    # inline. The promoted job then runs under the kernel budget below.
    execution_mode="adaptive",
    promotion_threshold_s=45,
    # Kernel budget for a promoted background job. Keep the one-hour maximum
    # aligned with the sidecar client ceiling; callers should submit one target
    # per job when runtime is uncertain.
    default_timeout=1800,
    max_timeout=3600,
    type="conda",
    dependency_file=ENVIRONMENT_YML,
    auto_build=True,
    additional_commands=[
        # Hash-locked RetroChimera, Syntheseus, and complete planning stack.
        f"python -m pip install --require-hashes -r {_REQUIREMENTS_FILE}",
        f"python -m pip install --no-deps {_PROVENANCE_PKG}",
        # In-kernel RetroChimera tools (declares no runtime deps).
        f"python -m pip install --no-deps {_RETRO_TOOLS_PKG}",
    ],
    # Load the ~10 GB planning model ONCE per container in a co-located sidecar
    # instead of inside every isolated kernel session (which OOM-killed the
    # host). Kernels reach it over loopback via RETROCHIMERA_MODEL_SERVICE_URL.
    # The rule-application worker pool size is taken from the container's
    # RETROCHIMERA_NUM_PROCESSES (see docker-compose.yml); when unset it uses the
    # library's cpu_count() default. It is intentionally NOT pinned here in
    # ``env`` so operators can tune it per host — the sidecar inherits os.environ,
    # and SidecarConfig.env would otherwise override it. cpu_count() is ideal on
    # large-memory hosts (more workers = smaller per-worker rulebase shard + more
    # parallel rule application = faster planning); set it low (~2) only on
    # RAM-constrained hosts. The sidecar runs in this server's kernel environment
    # (use_env_python) and inherits RETROCHIMERA_CHECKPOINT_DIR from the container.
    sidecars=[
        SidecarConfig(
            name="retrochimera-model",
            command=["-m", "retrochimera_tools.model_service"],
            url_env_var="RETROCHIMERA_MODEL_SERVICE_URL",
            port=8901,
            health_path="/health",
            readiness_timeout_s=600.0,
        ),
    ],
    peer_registry=peer_registry_for("retrochimera"),
)


class RetrochimeraServer(CodeExecutionServer):
    """RetroChimera-specific MCP server for retrosynthesis route prediction."""


tool_registry = ToolRegistry(package="retrochimera_tools")
for tool_def in RETROCHIMERA_TOOLS:
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

server = RetrochimeraServer(
    server_config=config,
    tool_registry=tool_registry,
    auth_config=create_noop_auth_config(),
    publishers=_publishers,
    skills=RETROCHIMERA_SKILLS,
    states=RETROCHIMERA_STATES,
)

if __name__ == "__main__":
    if "--warm" in sys.argv:
        asyncio.run(server.warm())
    else:
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        asyncio.run(server.run_http(host=host, port=port))
