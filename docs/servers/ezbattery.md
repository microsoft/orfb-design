# EZBattery cell simulation

The `ezbattery` server translates molecule-level predictions into device-level
redox-flow-battery metrics using a DHPS-ferrocyanide aqueous reference cell.

| Property | Value |
|---|---|
| Container | `ezbattery-server` |
| Host port | `8044` |
| Execution tool | `execute_ezbattery_code` |
| Skill | `ezbattery-cell-simulation` |
| External checkpoint | None |

## Domain tools

| Function | Purpose |
|---|---|
| `simulate_negolyte(...)` | Map reduction potential, solubility, electron count, and structural descriptors onto the reference-cell anode and return cell KPIs |
| `negolyte_sensitivity(...)` | Sweep uncertain diffusivity and kinetic-rate assumptions and report KPI ranges |
| `list_electrolyte_profiles()` | List calibrated and representative supporting-electrolyte regimes |
| `simulate_cell(overrides=None)` | Run the reference cell with validated low-level parameter overrides |

Returned KPIs include coulombic, voltage, and energy efficiency; charge and
discharge energy; cycle times; capacity fade; and a downsampled voltage/state-
of-charge curve.

Evaluation results include a compact `provenance` object with the pinned
EZBattery upstream commit plus applicability and uncertainty classifications.
Inputs, warnings, parameter provenance, and sensitivity factors remain in the
MCP call log or ordinary result.

## Skill guidance

The `ezbattery-cell-simulation` skill focuses on the gap between atomistic
predictions and cell-model inputs. It records whether each parameter was
predicted, estimated, literature-derived, user-supplied, or left at a reference
default. Agents are instructed to pair point simulations with sensitivity
analysis before trusting absolute KPI rankings.

Longer sensitivity sweeps can be promoted to background jobs in the same way as
other adaptive Agora Workbench servers.

## Open-source foundation

The physics simulator is
[`pnnl/EZBattery`](https://github.com/pnnl/EZBattery), developed by Pacific
Northwest National Laboratory. Upstream does not publish an installable Python
package, so the server fetches a pinned GitHub revision during the image build
and stages its Python modules inside the execution environment. The source is
used under its Simplified BSD license. Simulation is pure Python and runs on
CPU.
