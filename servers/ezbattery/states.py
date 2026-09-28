"""EZBattery cell-level RFB simulation domain state vocabulary."""

from enum import Enum


class EzbatteryState(str, Enum):
    """State tokens for the ezbattery cell-simulation tool graph."""

    NEGOLYTE_EVALUATED = "ezbattery.negolyte_evaluated"
    NEGOLYTE_SENSITIVITY_ANALYZED = "ezbattery.negolyte_sensitivity_analyzed"
    CELL_SIMULATED = "ezbattery.cell_simulated"


STATE_AFFORDANCES = {
    EzbatteryState.NEGOLYTE_EVALUATED: [
        "evaluate an ORFB negolyte candidate at the device level",
        "turn a reduction potential and solubility into cell KPIs",
        "rank negolyte candidates by cell energy density and efficiency",
    ],
    EzbatteryState.NEGOLYTE_SENSITIVITY_ANALYZED: [
        "bracket a negolyte candidate's KPIs against the physicochemical gap",
        "sweep the least-constrained inputs (diffusivity, rate constant) for error bars",
        "check whether a candidate ranking is robust to uncertain transport/kinetics",
    ],
    EzbatteryState.CELL_SIMULATED: [
        "simulate a redox-flow-battery cell charge/discharge cycle",
        "compute coulombic, voltage and energy efficiency for a cell",
        "sweep EZBattery cell parameters and inspect the voltage/SOC curve",
    ],
}
