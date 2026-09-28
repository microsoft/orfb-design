"""Cell-level ORFB simulation for the ezbattery server.

Thin wrapper over the in-kernel EZBattery model (``_model``).
"""

from __future__ import annotations

from typing import Optional

from ezbattery_tools import _model


def simulate_cell(overrides: Optional[dict] = None) -> dict:
    """Simulate the reference organic DHPS–ferrocyanide ORFB cell.

    Args:
        overrides: Optional mapping of EZBattery parameter names to override
            values (validated against the bundled reference-cell template).

    Returns:
        Dict with ``cell``, the applied ``overrides`` and a ``kpis`` block
        (per-cycle coulombic / voltage / energy efficiency, charge & discharge
        energy and times, capacity fade, and a downsampled cell-voltage / SOC
        curve).
    """
    return _model.simulate_cell(overrides)
