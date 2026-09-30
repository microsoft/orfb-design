"""Cell-level ORFB simulation for the ezbattery server.

Thin wrapper over the in-kernel EZBattery model (``_model``).
"""

from __future__ import annotations

from typing import Optional

from ezbattery_tools import _model
from ezbattery_tools._provenance import upstream_model_metadata
from orfb_provenance import attach_provenance


def simulate_cell(overrides: Optional[dict] = None) -> dict:
    """Simulate the reference organic DHPS–ferrocyanide ORFB cell.

    Args:
        overrides: Optional mapping of EZBattery parameter names to override
            values (validated against the bundled reference-cell template).

    Returns:
        Dict with ``cell``, the applied ``overrides`` and a ``kpis`` block
        (per-cycle coulombic / voltage / energy efficiency, charge & discharge
        energy and times, capacity fade, and a downsampled cell-voltage / SOC
        curve), plus a structured ``provenance`` envelope.
    """
    result = _model.simulate_cell(overrides)
    return attach_provenance(
        result,
        tool_name="simulate_cell",
        tool_distribution="ezbattery-tools",
        tool_version_fallback="0.1.0",
        inputs={"overrides": overrides},
        model=upstream_model_metadata(),
        configuration={
            "reference_cell": "organic_dhps_ferrocyanide",
            "applied_overrides": result.get("overrides", {}),
        },
        assumptions=[
            "The simulation uses the bundled DHPS-ferrocyanide reference-cell template except for explicit overrides.",
            "Simulation results are computational estimates and require experimental validation.",
        ],
        applicability={
            "status": "reference_configuration",
            "details": "Applicability outside the bundled reference-cell configuration is not calibrated.",
        },
        uncertainty={
            "quantified": False,
            "details": "simulate_cell returns point estimates and does not propagate parameter uncertainty.",
        },
    )
