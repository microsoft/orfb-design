# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Graphormer redox domain state vocabulary."""

from enum import Enum


class GraphormerState(str, Enum):
    """State tokens for the graphormer redox tool graph."""

    REDUCTION_PREDICTED = "graphormer.reduction_predicted"
    OXIDATION_PREDICTED = "graphormer.oxidation_predicted"


STATE_AFFORDANCES = {
    GraphormerState.REDUCTION_PREDICTED: [
        "predict the reduction potential of a molecule",
        "estimate anolyte redox potential (V vs SHE)",
        "rank candidates by reduction potential",
    ],
    GraphormerState.OXIDATION_PREDICTED: [
        "predict the oxidation potential of a molecule",
        "estimate catholyte redox potential (V vs SHE)",
        "rank candidates by oxidation potential",
    ],
}
