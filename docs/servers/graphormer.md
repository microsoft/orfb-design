# Graphormer redox prediction

The `graphormer` server predicts reduction and oxidation potentials for ORFB
candidate molecules.

| Property | Value |
|---|---|
| Container | `graphormer-server` |
| Host port | `8041` |
| Execution tool | `execute_graphormer_code` |
| Skill | `graphormer-redox` |
| Output unit | Volts versus SHE |

## Domain tools

| Function | Purpose |
|---|---|
| `predict_reduction_potential(smiles_list)` | Predict reduction potential for anolyte or negolyte screening |
| `predict_oxidation_potential(smiles_list)` | Predict oxidation potential for catholyte or posolyte screening |

Both functions accept up to 32 SMILES and return one result per molecule.
Inputs that fail graph conversion or exceed 128 non-hydrogen atoms are reported
as failures.

Results include a structured `provenance` object. It identifies the requested
checkpoint artifact, records when no checkpoint version is available, captures
the exact inputs and inference configuration, and states that the model provides
neither an applicability-domain score nor calibrated predictive uncertainty.

## Skill guidance

The `graphormer-redox` skill explains the potential reference frame, batch
limits, checkpoint requirements, and when to use SolTranNet instead. Redox
predictions are fast enough to run synchronously in batches.

## Runtime and assets

The container builds the public
[`microsoft/Graphormer`](https://github.com/microsoft/Graphormer) source at
commit
[`59c0dec`](https://github.com/microsoft/Graphormer/commit/59c0decffcade9df81d29dcc178a489b31958bab)
and its pinned Fairseq submodule. It reconstructs the model from Fairseq
state-dict checkpoints and runs CPU inference.

Two separately supplied files are required:

- `reduction_checkpoint_best.pt`
- `oxidation_checkpoint_best.pt`

Set `GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE` and
`GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE` before staging assets. This repository
does not currently provide a public download for compatible redox checkpoints.
