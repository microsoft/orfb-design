# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""ORFB domain state vocabulary (RDKit characterization server).

Defines the canonical state tokens for the ORFB server's RDKit tool graph.
``molecular_properties`` is the entry point; similarity and synthetic-
accessibility scoring consume a characterized molecule.

Redox potential prediction and retrosynthesis are owned by the ``graphormer``
and ``retrochimera`` peer servers and carry their own state vocabularies.
"""

from enum import Enum


class OrfbState(str, Enum):
    """State tokens for the ORFB characterization tool graph.

    Flow::

        molecular_properties -> PROPERTIES_COMPUTED
                                      |
                    +-----------------+-----------------+
                    v                                   v
            tanimoto_similarity                     sa_score
                    |                                   |
                    v                                   v
            SIMILARITY_SCORED                  SYNTHESIZABILITY_SCORED
    """

    PROPERTIES_COMPUTED = "orfb.properties_computed"
    SIMILARITY_SCORED = "orfb.similarity_scored"
    SYNTHESIZABILITY_SCORED = "orfb.synthesizability_scored"


STATE_AFFORDANCES = {
    OrfbState.PROPERTIES_COMPUTED: [
        "compute molecular descriptors for a candidate",
        "calculate molecular weight, LogP, TPSA, formal charge",
        "characterize a redox-flow-battery molecule",
    ],
    OrfbState.SIMILARITY_SCORED: [
        "score similarity of candidates to a target molecule",
        "rank molecules by Tanimoto similarity",
    ],
    OrfbState.SYNTHESIZABILITY_SCORED: [
        "score how easy a molecule is to synthesize",
        "compute synthetic accessibility (SA) score",
    ],
}
