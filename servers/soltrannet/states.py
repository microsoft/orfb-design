"""SolTranNet aqueous-solubility domain state vocabulary."""

from enum import Enum


class SoltrannetState(str, Enum):
    """State tokens for the soltrannet solubility tool graph."""

    SOLUBILITY_PREDICTED = "soltrannet.solubility_predicted"


STATE_AFFORDANCES = {
    SoltrannetState.SOLUBILITY_PREDICTED: [
        "predict the aqueous solubility (logS) of a molecule",
        "estimate ORFB electrolyte solubility in water",
        "rank candidates by aqueous solubility",
    ],
}
