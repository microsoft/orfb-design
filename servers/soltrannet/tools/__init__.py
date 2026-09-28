"""SolTranNet domain tool definitions.

Exports ``SOLTRANNET_TOOLS`` — server-side ``ToolDefinition`` metadata for the
aqueous-solubility (logS) predictor. The implementation lives in the
``soltrannet_tools`` package installed into the execution environment.
"""

from .definitions import predict_solubility

SOLTRANNET_TOOLS = [
    predict_solubility,
]

__all__ = ["SOLTRANNET_TOOLS"]
