# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Graphormer domain tool definitions.

Exports ``GRAPHORMER_TOOLS`` — server-side ``ToolDefinition`` metadata for the
redox potential predictors. Implementations live in the ``graphormer_tools``
package installed into the execution environment.
"""

from .definitions import predict_oxidation_potential, predict_reduction_potential

GRAPHORMER_TOOLS = [
    predict_reduction_potential,
    predict_oxidation_potential,
]

__all__ = ["GRAPHORMER_TOOLS"]
