# ORFB molecular characterization

The `orfb` server provides fast, deterministic molecule characterization using
RDKit. It is commonly the first server used in a screening campaign.

| Property | Value |
|---|---|
| Container | `orfb-server` |
| Host port | `8040` |
| Execution tool | `execute_orfb_code` |
| Skill | `orfb-design` |
| External checkpoint | None |

## Domain tools

| Function | Purpose |
|---|---|
| `molecular_properties(smiles_list, properties=None)` | Compute molecular weight, formula, LogP, H-bond counts, TPSA, rotatable bonds, ring counts, fraction sp3, heavy-atom count, and formal charge |
| `tanimoto_similarity(smiles_list, target_smiles)` | Compare candidates with a target using radius-2, 2,048-bit Morgan fingerprints |
| `sa_score(smiles_list)` | Compute RDKit synthetic-accessibility scores; lower values are generally easier to synthesize |

Characterize molecules before calling the similarity or synthetic-accessibility
functions. Invalid SMILES are returned as per-molecule failures rather than
aborting the complete batch.

Each evaluation result includes a compact `provenance` object with the RDKit and
tool versions plus applicability and uncertainty classifications. Inputs,
statuses, and failures remain in the MCP call log and ordinary result.

## Skill guidance

The `orfb-design` skill teaches an agent to:

1. validate and characterize a candidate set;
2. filter on descriptors such as molecular weight, charge, and LogP;
3. compare candidates with a reference scaffold;
4. score synthetic accessibility; and
5. hand selected candidates to Graphormer or RetroChimera.

The execution environment also preloads common RDKit, NumPy, and pandas
modules for exploratory analysis and visualization.

## Open-source foundation

The chemistry implementation uses [RDKit](https://github.com/rdkit/rdkit),
including its contributed SA Score implementation. No learned model or external
checkpoint is required.
