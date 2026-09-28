# SolTranNet aqueous solubility

The `soltrannet` server predicts aqueous solubility for candidate molecules as
logS, the base-10 logarithm of molar solubility.

| Property | Value |
|---|---|
| Container | `soltrannet-server` |
| Host port | `8043` |
| Execution tool | `execute_soltrannet_code` |
| Skill | `soltrannet-solubility` |
| External checkpoint | None |

## Domain tool

| Function | Purpose |
|---|---|
| `predict_solubility(smiles_list)` | Predict logS for up to 256 SMILES |

Results include the predicted `log_solubility`, status, and an optional
reliability warning. A value of `0` corresponds to 1 mol/L, `-2` to 0.01 mol/L,
and more negative values to lower predicted solubility.

## Skill guidance

The `soltrannet-solubility` skill explains logS interpretation and tells agents
to treat salts, unsupported atom types, and other out-of-distribution warnings
with additional caution.

## Open-source foundation

The model comes from
[`gnina/SolTranNet`](https://github.com/gnina/SolTranNet), an open-source
molecule-attention transformer trained on AqSolDB. Its trained weights ship
inside the Python package, so the server does not require a separately staged
checkpoint. Inference runs on CPU.
