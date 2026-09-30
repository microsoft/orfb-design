---
name: graphormer-redox
description: Predict reduction and oxidation potentials (volts versus SHE) for organic redox-flow-battery candidate molecules using the Graphormer redox model, via the predict_reduction_potential / predict_oxidation_potential tools and the execute_graphormer_code tool.
states:
  - graphormer.reduction_predicted
  - graphormer.oxidation_predicted
---

# Graphormer Redox Potentials

Use this skill to predict **redox potentials** for ORFB candidate molecules:

- `predict_reduction_potential(smiles_list=[...])` — reduction potential
  (anolyte selection), volts versus SHE.
- `predict_oxidation_potential(smiles_list=[...])` — oxidation potential
  (catholyte selection), volts versus SHE.

Both accept up to 32 SMILES per call and return one record per molecule with a
`potential`, `status`, and per-molecule `failure_reason`.

This server predicts redox potentials only. Use the `soltrannet` server for
aqueous-solubility prediction.

## Inference stack

Real predictions use the public Microsoft Graphormer source and its pinned
Fairseq submodule in a Python 3.9 environment. The two fine-tuned Fairseq
state-dict checkpoints must be available:

```
GRAPHORMER_CHECKPOINT_DIR=/path/to/checkpoints   # reduction + oxidation .pt files
GRAPHORMER_DEVICE=cpu                             # default image
```

The staged checkpoints are baked into the server's Docker image. The provided
image is configured for CPU inference; CUDA use requires a compatible custom
image and container runtime.

## Notes

- Inputs are SMILES strings; molecules with more than 128 non-hydrogen atoms or
  that fail graph conversion are reported as `status == "failed"`.
- Prediction is fast; run batches synchronously in a single
  `execute_graphormer_code` call.
- Preserve the top-level `provenance` object with downstream results. It records
  the checkpoint identifier and explicitly notes that no checkpoint version,
  applicability score, or calibrated uncertainty is available.
