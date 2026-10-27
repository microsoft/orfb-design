# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""In-kernel SolTranNet aqueous-solubility inference.

Wraps `SolTranNet <https://github.com/gnina/SolTranNet>`_ (Francoeur & Koes,
*J. Chem. Inf. Model.* 2021, doi:10.1021/acs.jcim.1c00331) — an open-source
(Apache-2.0) molecule-attention-transformer aqueous-solubility predictor trained
on AqSolDB — to run **inside the soltrannet CodeExecutionServer's kernel**. Its
output is ``logS`` (base-10 logarithm of the aqueous solubility ``S`` in mol/L).

SolTranNet ships its trained weights inside the pip package, so — unlike the
redox / retrosynthesis servers — there is **no external checkpoint to fetch or
bake**: inference is available whenever ``soltrannet`` imports successfully. The
heavy stack (``soltrannet``, ``torch``, ``rdkit``, ``numpy``) is imported lazily
so this module stays importable during server setup; real inference requires
that stack.

Inference runs on CPU.
"""

from __future__ import annotations

import functools
import os
from typing import Any, Optional

UNIT = "logS (log10 of aqueous solubility S in mol/L)"
PROPERTY_NAME = "aqueous_solubility"
MAX_BATCH_SIZE = 256


@functools.lru_cache(maxsize=1)
def _ensure_conda_libstdcpp_loaded() -> None:
    """Preload the conda env's ``libstdc++`` so RDKit's boost finds a new-enough CXXABI.

    The Agora kernel launches the env's interpreter directly (no ``conda
    activate``), so the env's ``lib/`` is not on the dynamic-linker path. The
    pip-installed ``torch`` wheel pulls in the older *system* ``libstdc++`` first;
    conda-forge RDKit's boost then fails to import with "version ``CXXABI_1.3.15``
    not found". Force-loading the env's newer ``libstdc++`` with ``RTLD_GLOBAL``
    up front makes the required symbols available regardless of import order.
    Idempotent and best-effort (a no-op if the library can't be located/loaded).
    """
    import ctypes
    import glob
    import sys

    candidates = sorted(glob.glob(os.path.join(sys.prefix, "lib", "libstdc++.so*")))
    for lib in reversed(candidates):
        try:
            ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
            return
        except OSError:
            continue


@functools.lru_cache(maxsize=1)
def _predict_fn() -> Any:
    """Return SolTranNet's ``predict`` callable (imports torch/rdkit lazily)."""
    import soltrannet as stn

    return stn.predict


def _valid_smiles(smiles: str) -> bool:
    """Whether RDKit can parse *smiles* into a molecule.

    SolTranNet's featurizer calls ``mol.GetAtoms()`` without a ``None`` guard, so
    an unparseable SMILES raises and aborts the whole batch. We pre-screen with
    RDKit and only hand valid molecules to the model, recording the rest as
    per-molecule failures.
    """
    from rdkit import Chem

    return Chem.MolFromSmiles(smiles) is not None


def run_real_inference(smiles_list: list[str]) -> list[dict]:
    """Run real SolTranNet inference, one result dict per input SMILES.

    Raises on environment/model problems.
    """
    _ensure_conda_libstdcpp_loaded()
    import torch

    results: list[Optional[dict]] = [None] * len(smiles_list)
    valid_indices: list[int] = []
    valid_smiles: list[str] = []
    for index, smiles in enumerate(smiles_list):
        if _valid_smiles(smiles):
            valid_indices.append(index)
            valid_smiles.append(smiles)
        else:
            results[index] = {
                "smiles": smiles,
                "status": "failed",
                "log_solubility": None,
                "unit": UNIT,
                "warning": None,
                "failure_reason": "SMILES could not be parsed by RDKit",
            }

    if valid_smiles:
        # SolTranNet yields (prediction, smiles, warning) tuples in the order of
        # the list it is given (re-sorted by original index internally), so the
        # k-th output corresponds to valid_indices[k].
        predictions = list(_predict_fn()(valid_smiles, device=torch.device("cpu")))
        for valid_idx, (logs, _smiles, warning) in zip(valid_indices, predictions):
            warn = warning.strip() if isinstance(warning, str) and warning.strip() else None
            results[valid_idx] = {
                "smiles": smiles_list[valid_idx],
                "status": "succeeded",
                "log_solubility": round(float(logs), 4),
                "unit": UNIT,
                "warning": warn,
                "failure_reason": None,
            }

    # Defensive: any slot SolTranNet did not return for becomes a failure.
    for index, smiles in enumerate(smiles_list):
        if results[index] is None:
            results[index] = {
                "smiles": smiles,
                "status": "failed",
                "log_solubility": None,
                "unit": UNIT,
                "warning": None,
                "failure_reason": "SolTranNet returned no prediction for this molecule",
            }

    return [r for r in results if r is not None]


def predict(smiles_list: list[str]) -> dict:
    """Predict aqueous solubility (logS) per molecule with SolTranNet.

    Requires the SolTranNet stack; raises if it is unavailable.
    """
    if not isinstance(smiles_list, list) or not smiles_list:
        raise ValueError("smiles_list must be a non-empty list of SMILES strings")
    if len(smiles_list) > MAX_BATCH_SIZE:
        raise ValueError(f"A maximum of {MAX_BATCH_SIZE} SMILES strings is supported per request")
    if not all(isinstance(s, str) and s.strip() for s in smiles_list):
        raise ValueError("smiles_list must contain only non-empty SMILES strings")

    return {
        "property_name": PROPERTY_NAME,
        "unit": UNIT,
        "num_molecules": len(smiles_list),
        "predictions": run_real_inference(smiles_list),
    }


# Load the conda env's libstdc++ at import time — before any user ``import
# torch`` in the kernel can pull in the older system libstdc++ — so RDKit's boost
# always finds a new-enough CXXABI regardless of subsequent import order. The
# tool module is imported during proxy injection ahead of user code, so this runs
# first in practice. Best-effort: a no-op outside the conda kernel.
_ensure_conda_libstdcpp_loaded()
