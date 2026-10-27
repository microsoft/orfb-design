# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""EZBattery domain tool definitions.

Exports ``EZBATTERY_TOOLS`` — server-side ``ToolDefinition`` metadata for the
cell-level RFB simulation tools. The implementation lives in the
``ezbattery_tools`` package installed into the execution environment.
"""

from .definitions import (
    list_electrolyte_profiles,
    negolyte_sensitivity,
    simulate_cell,
    simulate_negolyte,
)

EZBATTERY_TOOLS = [
    simulate_negolyte,
    negolyte_sensitivity,
    simulate_cell,
    list_electrolyte_profiles,
]

__all__ = ["EZBATTERY_TOOLS"]
