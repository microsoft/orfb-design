---
name: soltrannet-solubility
description: Predict aqueous solubility (logS) for organic redox-flow-battery candidate molecules using the open-source SolTranNet model (trained on AqSolDB), via the predict_solubility tool and the execute_soltrannet_code tool.
states:
  - soltrannet.solubility_predicted
---

# SolTranNet Aqueous Solubility

Use this skill to predict the **aqueous solubility** of ORFB candidate molecules
— a key property for water-based redox-flow-battery electrolytes.

- `predict_solubility(smiles_list=[...])` — predicts solubility for up to 256
  molecules at once. Returns a record per molecule with `log_solubility`
  (**logS**, the base-10 logarithm of the solubility `S` in mol/L), `status`
  (`succeeded` / `failed`), an optional `warning`, and `failure_reason`.

## Interpreting logS

`logS` is `log10(S)` where `S` is the aqueous solubility in mol/L. Higher (less
negative) is more soluble:

- `logS = 0` → 1 mol/L
- `logS = -2` → 0.01 mol/L
- `logS = -5` → very poorly soluble

## Reliability warnings

SolTranNet flags inputs whose predictions are less reliable via the per-molecule
`warning` field (e.g. salts containing a `.` or molecules with atom types outside
its training distribution). Treat warned predictions with extra caution.

## Notes

- The model is open-source SolTranNet (Francoeur & Koes, *J. Chem. Inf. Model.*
  2021), a molecule-attention transformer trained on AqSolDB. Its trained
  weights ship inside the package, so no external checkpoint is required.
- Unparseable SMILES are reported per-molecule as `status="failed"` rather than
  aborting the batch.
- Inference runs on CPU and is fast; large lists return quickly.
- Preserve the top-level `provenance` object; it records installed versions and
  compact applicability and uncertainty classifications. Per-molecule
  reliability warnings remain in the ordinary prediction records.
