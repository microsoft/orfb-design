---
name: orfb-design
description: Organic redox-flow-battery (ORFB) molecule characterization with RDKit — physicochemical descriptors, Tanimoto similarity to a target, and synthetic accessibility scoring, via domain tools and the execute_orfb_code tool. Redox potentials and retrosynthesis are served by the graphormer and retrochimera peer servers.
states:
  - orfb.properties_computed
  - orfb.similarity_scored
  - orfb.synthesizability_scored
---

# ORFB Molecule Characterization

Use this skill when the user is designing or screening molecules for **organic
redox-flow batteries (ORFB)** and needs RDKit-based characterization —
physicochemical descriptors, similarity to a reference scaffold, or synthetic
accessibility. Code runs in the `execute_orfb_code` tool with RDKit
auto-imported.

For **redox potentials** (reduction / oxidation) and **retrosynthesis**, use the
dedicated peer servers in the ORFB network (`graphormer` and `retrochimera`),
reachable through the same `orfb-hub` router. Hand a candidate set to a peer
kernel with `orfb_send(to="graphormer")` or `orfb_send(to="retrochimera")`.

Always set `description` on each `execute_orfb_code` call to a one-line summary
of what the code does and why. It is shown to the user watching the server.

## Tool Graph Overview

`molecular_properties` is the entry point — characterize candidates first, then
score similarity and synthesizability.

```
molecular_properties -> orfb.properties_computed
        |
        +-- tanimoto_similarity -> orfb.similarity_scored
        +-- sa_score            -> orfb.synthesizability_scored
```

## Tools

| Tool | Purpose |
|------|---------|
| `molecular_properties` | RDKit descriptors (MW, formula, LogP, HBD/HBA, TPSA, rings, formal charge, ...) |
| `tanimoto_similarity` | Tanimoto similarity to a target (Morgan, r=2, 2048 bits) |
| `sa_score` | Synthetic accessibility score (1-10, lower is easier) |

## Auto-Imported Modules

Available without explicit imports inside `execute_orfb_code`:

```python
from rdkit import Chem
from rdkit.Chem import Draw, Descriptors, AllChem, rdMolDescriptors, PandasTools
import numpy as np
import pandas as pd
```

## Critical: SMILES Validation

Always check that `Chem.MolFromSmiles()` did not return `None` before using a
molecule -- invalid SMILES silently return `None` and crash on the next call.
The domain tools already validate input and report per-molecule failures in
their `results` list with `status == "failed"`.

## Typical Design Workflow (across the ORFB network)

1. `molecular_properties(smiles_list=...)` -- characterize candidates; drop ones
   with undesirable MW / charge / LogP.
2. On the `graphormer` peer: `predict_reduction_potential` /
   `predict_oxidation_potential` -- rank by redox potential for the target
   electrode.
3. `tanimoto_similarity(smiles_list=..., target_smiles=...)` -- keep candidates
   close to a known-good reference scaffold.
4. `sa_score(smiles_list=...)` -- prefer easier-to-synthesize molecules (lower).
5. On the `retrochimera` peer: `predict_retrosynthesis(smiles=...)` -- confirm a
   viable route to purchasable starting materials for the top candidates.

## Provenance

Every evaluation tool returns a top-level `provenance` object. Preserve it when
passing results between agents or peers; it records exact inputs, tool/model
versions, configuration, normalized status and failures, assumptions,
applicability guidance, and uncertainty scope.
