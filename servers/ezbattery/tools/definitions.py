"""Tool definitions (metadata) for the ezbattery cell-simulation domain.

Server-side schemas only — the implementation lives in the ``ezbattery_tools``
package installed into the execution kernel. These tools wrap the open-source
EZBattery (PNNL, Simplified BSD) cell/system-level RFB physics simulator to
close the ORFB design loop at the *device* level, downstream of the molecular
predictors (graphormer, soltrannet, retrochimera).
"""

from agora_workbench.code_execution import ReturnSpec, StateTransition, ToolDefinition, ToolParameter

simulate_negolyte = ToolDefinition(
    name="simulate_negolyte",
    module="ezbattery_tools.negolyte",
    description=(
        "Evaluate an ORFB negolyte (anode-side species) at the device level with "
        "EZBattery. Maps molecule-level predictions — reduction standard "
        "potential (V), aqueous solubility (mol/L) and electrons per molecule — "
        "onto the anode of a validated organic DHPS-ferrocyanide reference cell, "
        "runs a charge/discharge simulation, and returns cell KPIs (coulombic / "
        "voltage / energy efficiency, charge & discharge energy, cycle times, "
        "capacity fade and a downsampled voltage/SOC curve). Optionally also "
        "bridges the physicochemical gap to the cell model: pass a SMILES to have "
        "molar mass and formal charge derived automatically via RDKit, where "
        "molar mass sets the bulk diffusivity via a Stokes-Einstein estimate and "
        "formal charge sets the redox valences, with every override tagged in a "
        "parameter_provenance block as predicted / estimated / assumed_default."
    ),
    required_parameters=[
        ToolParameter(
            name="standard_potential",
            type=float,
            description=(
                "Reduction standard potential of the negolyte couple in volts, on "
                "the same reference (SHE) as the cell's ferro/ferricyanide posolyte."
            ),
        ),
    ],
    optional_parameters=[
        ToolParameter(
            name="solubility_mol_per_L",
            type=float,
            description="Aqueous solubility of the active species in mol/L (e.g. 10**logS from soltrannet).",
        ),
        ToolParameter(
            name="electron_number",
            type=int,
            description="Electrons transferred per molecule (e.g. 2 for a two-electron negolyte).",
        ),
        ToolParameter(name="name", type=str, description="Optional label for the candidate, echoed back."),
        ToolParameter(
            name="smiles",
            type=str,
            description=(
                "SMILES of the active species; when given, molar mass and formal "
                "charge are computed from it via RDKit (deterministic descriptors) "
                "unless passed explicitly, which takes precedence."
            ),
        ),
        ToolParameter(
            name="molar_mass",
            type=float,
            description=(
                "Molar mass (g/mol); usually derived from smiles, pass only to "
                "override. Used to estimate the bulk diffusivity via Stokes-Einstein."
            ),
        ),
        ToolParameter(
            name="formal_charge",
            type=int,
            description=(
                "Net formal charge of the oxidized species; usually derived from "
                "smiles. Sets the redox valences (crossover/Donnan)."
            ),
        ),
        ToolParameter(
            name="active_density_kg_per_m3",
            type=float,
            description="Assumed condensed-phase density used only for the diffusivity estimate (default ~1400).",
        ),
        ToolParameter(
            name="reaction_rate_constant",
            type=float,
            description="Optional electrochemical rate constant (m/s); left at the DHPS default if omitted.",
        ),
        ToolParameter(
            name="electrolyte_profile",
            type=str,
            description=(
                "Optional supporting-electrolyte regime name (see list_electrolyte_profiles) "
                "setting the anode viscosity/density/conductivity; all profiles are "
                "literature-calibrated except 'polymer_laden', which is a representative "
                "high-viscosity stress test."
            ),
        ),
        ToolParameter(
            name="extra_overrides",
            type=dict,
            description="Optional additional EZBattery parameter overrides (validated against the template).",
        ),
    ],
    return_spec=[
        ReturnSpec(name="cell", type=str, description="Reference cell id ('organic_dhps_ferrocyanide')"),
        ReturnSpec(name="overrides", type=dict, description="EZBattery parameters that were overridden"),
        ReturnSpec(
            name="kpis", type=dict, description="Per-cycle efficiencies, energies, times, fade and voltage curve"
        ),
        ReturnSpec(
            name="negolyte", type=dict, description="Echoed inputs, estimated diffusivity and the anode parameters set"
        ),
        ReturnSpec(
            name="parameter_provenance",
            type=list,
            description="Per-override records: predicted / estimated / assumed_default / user",
        ),
        ReturnSpec(name="warnings", type=list, description="Reference-frame and other sanity warnings"),
    ],
    state_transition=StateTransition(
        produces=frozenset({"ezbattery.negolyte_evaluated", "ezbattery.cell_simulated"}),
    ),
    affordances=[
        "evaluate an ORFB negolyte candidate at the device level",
        "turn a reduction potential and solubility into cell KPIs",
        "rank negolyte candidates by cell energy density and efficiency",
    ],
)

negolyte_sensitivity = ToolDefinition(
    name="negolyte_sensitivity",
    module="ezbattery_tools.negolyte",
    description=(
        "Bracket an ORFB negolyte's headline cell KPIs over its two most "
        "uncertain physical inputs — bulk diffusivity and the kinetic rate "
        "constant, the parameters least constrained by the atomistic predictors. "
        "Sweeps both over multiplicative factors around the baseline negolyte "
        "mapping and reports the KPI spread, so candidates can be ranked with "
        "error bars rather than a single point estimate. Returns no voltage curves."
    ),
    required_parameters=[
        ToolParameter(
            name="standard_potential",
            type=float,
            description="Reduction standard potential of the negolyte couple in volts (SHE frame).",
        ),
    ],
    optional_parameters=[
        ToolParameter(
            name="solubility_mol_per_L",
            type=float,
            description="Aqueous solubility of the active species in mol/L.",
        ),
        ToolParameter(name="electron_number", type=int, description="Electrons transferred per molecule."),
        ToolParameter(name="name", type=str, description="Optional label for the candidate, echoed back."),
        ToolParameter(
            name="smiles",
            type=str,
            description="SMILES of the active species; auto-derives molar mass and formal charge via RDKit.",
        ),
        ToolParameter(name="molar_mass", type=float, description="Molar mass (g/mol); usually derived from smiles."),
        ToolParameter(name="formal_charge", type=int, description="Net formal charge of the oxidized species."),
        ToolParameter(
            name="active_density_kg_per_m3",
            type=float,
            description="Assumed density used only for the diffusivity estimate (default ~1400).",
        ),
        ToolParameter(
            name="reaction_rate_constant",
            type=float,
            description="Optional baseline electrochemical rate constant (m/s).",
        ),
        ToolParameter(
            name="electrolyte_profile",
            type=str,
            description=(
                "Optional supporting-electrolyte regime name (see list_electrolyte_profiles); "
                "all profiles are literature-calibrated except 'polymer_laden'."
            ),
        ),
        ToolParameter(
            name="diffusivity_factors",
            type=list,
            description="Multipliers on the baseline anode diffusivity (default [0.3, 1.0, 3.0]).",
        ),
        ToolParameter(
            name="rate_constant_factors",
            type=list,
            description="Multipliers on the baseline anode rate constant (default [0.1, 1.0, 10.0]).",
        ),
        ToolParameter(
            name="extra_overrides",
            type=dict,
            description="Optional additional EZBattery parameter overrides (validated against the template).",
        ),
    ],
    return_spec=[
        ReturnSpec(name="cell", type=str, description="Reference cell id ('organic_dhps_ferrocyanide')"),
        ReturnSpec(name="baseline", type=dict, description="Headline KPIs at the baseline (unscaled) mapping"),
        ReturnSpec(name="ranges", type=dict, description="Per-KPI min / max / span over the sweep grid"),
        ReturnSpec(name="grid", type=list, description="(diffusivity_factor, rate_constant_factor) -> headline KPIs"),
        ReturnSpec(name="warnings", type=list, description="Reference-frame and other sanity warnings"),
    ],
    state_transition=StateTransition(
        produces=frozenset({"ezbattery.negolyte_sensitivity_analyzed", "ezbattery.negolyte_evaluated"}),
    ),
    affordances=[
        "quantify how much a negolyte's KPIs depend on uncertain diffusivity / kinetics",
        "attach error bars to a negolyte's cell performance",
        "check whether a candidate ranking is robust to the physicochemical gap",
    ],
)

simulate_cell = ToolDefinition(
    name="simulate_cell",
    module="ezbattery_tools.cell",
    description=(
        "Simulate the validated organic DHPS-ferrocyanide ORFB reference cell "
        "with EZBattery, optionally overriding any of the ~205 cell/electrolyte "
        "parameters in the bundled template. Runs a charge/discharge cycle and "
        "returns cell KPIs (coulombic / voltage / energy efficiency, charge & "
        "discharge energy, cycle times, capacity fade and a downsampled "
        "voltage/SOC curve)."
    ),
    optional_parameters=[
        ToolParameter(
            name="overrides",
            type=dict,
            description="Mapping of EZBattery parameter names to override values (validated against the template).",
        ),
    ],
    return_spec=[
        ReturnSpec(name="cell", type=str, description="Reference cell id ('organic_dhps_ferrocyanide')"),
        ReturnSpec(name="overrides", type=dict, description="EZBattery parameters that were overridden"),
        ReturnSpec(
            name="kpis", type=dict, description="Per-cycle efficiencies, energies, times, fade and voltage curve"
        ),
    ],
    state_transition=StateTransition(
        produces=frozenset({"ezbattery.cell_simulated"}),
    ),
    affordances=[
        "simulate a redox-flow-battery cell charge/discharge cycle",
        "compute coulombic, voltage and energy efficiency for a cell",
        "sweep EZBattery cell parameters and inspect the voltage/SOC curve",
    ],
)

list_electrolyte_profiles = ToolDefinition(
    name="list_electrolyte_profiles",
    module="ezbattery_tools.negolyte",
    description=(
        "List the named supporting-electrolyte profiles available to "
        "simulate_negolyte / negolyte_sensitivity via their electrolyte_profile "
        "argument. Each profile sets the anode-side viscosity, density and ionic "
        "conductivity for a regime (active-loaded DHPS reference, concentrated "
        "KOH, concentrated H2SO4, near-neutral supporting salt, polymer/nanofluid). "
        "All profiles are calibrated against literature/reference-cell data except "
        "'polymer_laden', a representative high-viscosity stress test flagged by "
        "calibrated=False."
    ),
    return_spec=[
        ReturnSpec(name="name", type=str, description="Profile id to pass as electrolyte_profile"),
        ReturnSpec(name="label", type=str, description="Human-readable regime description"),
        ReturnSpec(
            name="calibrated",
            type=bool,
            description="Whether the values are literature-calibrated (else representative)",
        ),
        ReturnSpec(
            name="citation", type=str, description="Literature source (or representative note for polymer_laden)"
        ),
        ReturnSpec(name="params", type=dict, description="Anode viscosity / density / conductivity the profile sets"),
    ],
    affordances=[
        "discover the supporting-electrolyte regimes available for negolyte simulation",
        "see which electrolyte profiles are calibrated vs representative",
        "look up the viscosity / density / conductivity a profile applies",
    ],
)
