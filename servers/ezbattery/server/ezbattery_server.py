"""EZBattery Cell-Level RFB Simulation MCP Server — device-level ORFB evaluation.

Provides an ``execute_ezbattery_code`` MCP tool plus ``simulate_negolyte``,
``negolyte_sensitivity`` and ``simulate_cell`` domain tools, backed by the
open-source `EZBattery
<https://github.com/pnnl/EZBattery>`_ (Pacific Northwest National Laboratory;
Simplified BSD) cell/system-level redox-flow-battery physics simulator loaded
**in-kernel**. Where the molecular servers (graphormer, soltrannet,
retrochimera) predict *molecule-level* properties, this server closes the ORFB
design loop at the *device* level: it maps molecular predictions onto a
validated organic DHPS-ferrocyanide reference cell and reports cell KPIs
(coulombic / voltage / energy efficiency, charge & discharge energy, cycle times
and the voltage/SOC curve).

EZBattery is pure Python (numpy / scipy / pandas / openpyxl / ismember) and its
source is fetched from a pinned upstream GitHub commit during the image build
because upstream ships no installable Python package. There is no external
checkpoint to fetch or bake. The numeric stack is installed into the conda
kernel at build time (see ``ENVIRONMENT_YML`` / ``additional_commands``).
Simulation runs on CPU.

Usage:
    python -m servers.ezbattery.server.ezbattery_server
"""

import asyncio
import os
import sys
from pathlib import Path

from agora_workbench.code_execution import CodeExecutionServer, ServerConfig, Skill, State, ToolRegistry
from agora_workbench.code_execution.auth import create_noop_auth_config
from agora_workbench.code_execution.data_access import AssetPublisher, BlobPublisher, LocalFilePublisher
from agora_workbench.code_execution.data_access.credentials import create_storage_credential

from servers.ezbattery.states import STATE_AFFORDANCES, EzbatteryState
from servers.ezbattery.tools import EZBATTERY_TOOLS
from servers.peers import peer_registry_for

_EZBATTERY_TOOLS_PKG = str(Path(__file__).resolve().parent.parent / "ezbattery_tools")
_PROVENANCE_PKG = str(Path(__file__).resolve().parents[2] / "provenance_tools")
_ENVIRONMENT_FILE = Path(__file__).resolve().parent.parent / "environment.yml"
_SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "SKILL.md"

EZBATTERY_SKILLS = [
    Skill(
        name="ezbattery-cell-simulation",
        description=(
            "Evaluate ORFB negolyte candidates and full cells at the device level "
            "with the open-source EZBattery physics simulator (PNNL), via the "
            "simulate_negolyte / negolyte_sensitivity / simulate_cell tools and the "
            "execute_ezbattery_code tool. Turns molecule-level predictions "
            "(reduction potential, solubility, electron count, molar mass, formal "
            "charge) into cell KPIs with per-parameter provenance and error bars."
        ),
        domain="ezbattery",
        states=[state.value for state in EzbatteryState],
        content=_SKILL_PATH.read_text(encoding="utf-8"),
        path=str(_SKILL_PATH),
    ),
]

EZBATTERY_STATES = [
    State(state.value, description=state.name.replace("_", " ").title(), affordances=STATE_AFFORDANCES[state])
    for state in EzbatteryState
]

# EZBattery simulation environment (see environment.yml). The interpreter, Agora
# kernel bits and the numeric stack (numpy<2, scipy, pandas, openpyxl) come from
# conda; the pip-only ``ismember`` helper and the in-kernel tools package (which
# contains the staged upstream EZBattery source) are pip-installed below.
ENVIRONMENT_YML = _ENVIRONMENT_FILE.read_text(encoding="utf-8")

config = ServerConfig(
    name="ezbattery",
    description=(
        "Execute Python code to evaluate organic redox-flow-battery designs at "
        "the device level with the open-source EZBattery simulator (PNNL). Domain "
        "tools: simulate_negolyte (map a negolyte's reduction potential, "
        "solubility, electron count, molar mass and formal charge onto a "
        "validated organic DHPS-ferrocyanide reference cell and report cell KPIs "
        "with per-parameter provenance), negolyte_sensitivity (bracket those KPIs "
        "over the uncertain diffusivity / kinetics) and simulate_cell (simulate "
        "the reference cell with arbitrary parameter overrides)."
    ),
    # Most cell simulations return quickly, but a negolyte_sensitivity sweep runs
    # several simulations back-to-back and can exceed a synchronous request
    # timeout. Run in ``adaptive`` mode as a safety net: calls start
    # synchronously and only promote to a background job (polled with
    # ezbattery_check_job) if they run past ``promotion_threshold_s``; quick
    # single simulations still return inline.
    execution_mode="adaptive",
    promotion_threshold_s=45,
    type="conda",
    dependency_file=ENVIRONMENT_YML,
    auto_build=True,
    additional_commands=[
        # Small pip-only helper EZBattery imports (not on conda-forge).
        "python -m pip install ismember",
        f"python -m pip install --no-deps {_PROVENANCE_PKG}",
        # In-kernel tools package with the staged upstream EZBattery modules.
        f"python -m pip install --no-deps {_EZBATTERY_TOOLS_PKG}",
    ],
    peer_registry=peer_registry_for("ezbattery"),
)


class EzbatteryServer(CodeExecutionServer):
    """EZBattery-specific MCP server for cell-level RFB simulation."""


tool_registry = ToolRegistry(package="ezbattery_tools")
for tool_def in EZBATTERY_TOOLS:
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

server = EzbatteryServer(
    server_config=config,
    tool_registry=tool_registry,
    auth_config=create_noop_auth_config(),
    publishers=_publishers,
    skills=EZBATTERY_SKILLS,
    states=EZBATTERY_STATES,
)

if __name__ == "__main__":
    if "--warm" in sys.argv:
        asyncio.run(server.warm())
    else:
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        asyncio.run(server.run_http(host=host, port=port))
