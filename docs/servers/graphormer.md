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
checkpoint artifact, records when no checkpoint version is available, and
states that the model provides neither an applicability-domain score nor
calibrated predictive uncertainty.

## Skill guidance

The `graphormer-redox` skill explains the potential reference frame, batch
limits, checkpoint requirements, and when to use SolTranNet instead. Redox
predictions are fast enough to run synchronously in batches.

## Open-source foundation

The model implementation comes from
[`microsoft/Graphormer`](https://github.com/microsoft/Graphormer) source at
commit
[`59c0dec`](https://github.com/microsoft/Graphormer/commit/59c0decffcade9df81d29dcc178a489b31958bab)
and its pinned Fairseq submodule. RDKit, DGL, PyTorch, and PyTorch Geometric
provide the molecular graph and model runtime.

## Runtime and assets

The server reconstructs Graphormer models from Fairseq state-dict checkpoints
and runs inference on CPU.

Both ORFB checkpoints use the `graphormer_base` architecture: 12 encoder
layers, a 768-dimensional embedding, 32 attention heads, and one scalar
regression output. These details come from the published checkpoint manifest
and match the model configuration loaded by this repository.

Two checkpoint files are staged from a revision-pinned, checksum-verified
[`microsoft/Graphormer`](https://huggingface.co/microsoft/Graphormer/tree/main/orfb-design/checkpoints)
Hugging Face release:

| Property | Hosted artifact | Staged filename | SHA-256 |
|---|---|---|---|
| Reduction | `graphormer_reduction.pt` | `reduction_checkpoint_best.pt` | `8893ba5b4de6dd541f59a070e517119f9828073f227bbe5082e25ea6d8e3bc8a` |
| Oxidation | `graphormer_oxidation.pt` | `oxidation_checkpoint_best.pt` | `2961e45c906a177c398aa61b9c3b2d28259e88e1f88aae787e77e8b72f21c8f5` |

The pinned Hugging Face revision is
[`8394616`](https://huggingface.co/microsoft/Graphormer/tree/83946163d6575dd35a6a030d9bea7460e0bc2252/orfb-design/checkpoints).
Hugging Face hosts downloadable model artifacts, not an ORFB Design inference
endpoint; inference runs inside the local Graphormer container.

Run `make graphormer-checkpoints` to download and stage them. Set
`GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE` or
`GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE` only when overriding a hosted
checkpoint with a local file.
