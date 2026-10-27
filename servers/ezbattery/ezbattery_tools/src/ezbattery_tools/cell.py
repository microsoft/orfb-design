# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Cell-level ORFB simulation for the ezbattery server.

Thin wrapper over the in-kernel EZBattery model (``_model``).
"""

from __future__ import annotations

from typing import Optional

from orfb_provenance import attach_provenance

from ezbattery_tools import _model
from ezbattery_tools._provenance import upstream_model_metadata


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
        tool_distribution="ezbattery-tools",
        tool_version_fallback="0.1.0",
        model=upstream_model_metadata(),
        applicability="reference_configuration",
        uncertainty="not_quantified",
    )
