"""RetroChimera retrosynthesis domain state vocabulary."""

from enum import Enum


class RetrochimeraState(str, Enum):
    """State tokens for the retrochimera tool graph."""

    ROUTES_PREDICTED = "retrochimera.routes_predicted"


STATE_AFFORDANCES = {
    RetrochimeraState.ROUTES_PREDICTED: [
        "plan a retrosynthesis route for a molecule",
        "assess synthesizability from purchasable building blocks",
        "identify starting materials for a target molecule",
    ],
}
