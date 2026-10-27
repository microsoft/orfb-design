# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Graphormer redox model loading and inference.

The checkpoints are standard Fairseq training checkpoints containing a model
state dict. The loader reconstructs the public Microsoft Graphormer model from
the saved architecture arguments, disables the training-time pretrained-model
source, and strict-loads the state dict.
"""

from __future__ import annotations

import argparse
import functools
import os
from typing import Any

UNIT = "V versus SHE"
MAX_BATCH_SIZE = 32
MAX_ATOMS = 128

REDOX_PROPERTIES: dict[str, dict[str, str]] = {
    "reduction": {"checkpoint": "reduction_checkpoint_best.pt"},
    "oxidation": {"checkpoint": "oxidation_checkpoint_best.pt"},
}

_MODEL_ARG_NAMES = {
    "act_dropout",
    "activation_fn",
    "apply_graphormer_init",
    "arch",
    "attention_dropout",
    "dropout",
    "edge_type",
    "encoder_attention_heads",
    "encoder_embed_dim",
    "encoder_ffn_embed_dim",
    "encoder_layers",
    "encoder_normalize_before",
    "max_nodes",
    "multi_hop_max_dist",
    "no_token_positional_embeddings",
    "num_atoms",
    "num_classes",
    "num_edge_dis",
    "num_edges",
    "num_in_degree",
    "num_out_degree",
    "num_spatial",
    "pre_layernorm",
    "remove_head",
    "share_encoder_input_output_embed",
    "spatial_pos_max",
}
_REQUIRED_MODEL_ARGS = {
    "edge_type",
    "encoder_attention_heads",
    "encoder_embed_dim",
    "encoder_ffn_embed_dim",
    "encoder_layers",
    "max_nodes",
    "multi_hop_max_dist",
    "num_atoms",
    "num_classes",
    "num_edge_dis",
    "num_edges",
    "num_in_degree",
    "num_out_degree",
    "num_spatial",
    "spatial_pos_max",
}


def checkpoint_dir() -> str | None:
    """Return the configured checkpoint directory, or ``None`` if unset/missing."""
    path = os.getenv("GRAPHORMER_CHECKPOINT_DIR", "").strip()
    return path if path and os.path.isdir(path) else None


@functools.lru_cache(maxsize=1)
def _ensure_cpu_compiler_on_path() -> None:
    """Make a C/C++ compiler discoverable for torch's runtime kernel fuser.

    The Agora kernel launches the env's interpreter directly (no ``conda
    activate``), so ``$CONDA_PREFIX/bin`` — which holds the conda compiler and
    the ``which`` shim — is not on ``PATH``. torch's TorchScript CPU fuser
    compiles fused kernels at inference time via a compiler it looks up on
    ``PATH`` (defaulting to ``c++``); when absent it raises "Failed to compile a
    fused CPU kernel". Prepend the env ``bin`` to ``PATH``, ensure a ``c++``
    alias exists, and pin ``CC``/``CXX`` so compilation succeeds. Idempotent.
    """
    import sys

    env_bin = os.path.join(sys.prefix, "bin")
    if not os.path.isdir(env_bin):
        return
    if env_bin not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = env_bin + os.pathsep + os.environ.get("PATH", "")

    # torch's fuser defaults to the ``c++`` command; the conda env only ships
    # the prefixed ``x86_64-conda-linux-gnu-c++`` plus an unprefixed ``g++``.
    cxx = os.path.join(env_bin, "c++")
    if not os.path.exists(cxx):
        for candidate in ("g++", "x86_64-conda-linux-gnu-c++"):
            src = os.path.join(env_bin, candidate)
            if os.path.exists(src):
                try:
                    os.symlink(candidate, cxx)
                except OSError:
                    pass
                break
    os.environ.setdefault("CC", "gcc")
    os.environ.setdefault("CXX", "g++")


def _device() -> str:
    """Resolve the torch device, falling back to CPU when CUDA is unavailable."""
    requested = os.getenv("GRAPHORMER_DEVICE", "cpu")
    try:
        import torch

        if requested.startswith("cuda") and not torch.cuda.is_available():
            return "cpu"
    except Exception:  # noqa: BLE001 - torch missing -> caller will raise
        return requested
    return requested


def _config_values(value: Any) -> dict[str, Any]:
    """Convert a saved Fairseq config section to a plain dictionary."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(vars(value))
    except TypeError as exc:
        raise ValueError(f"unsupported checkpoint config section: {type(value).__name__}") from exc


def _model_args(checkpoint: dict[str, Any]) -> argparse.Namespace:
    """Build inference arguments from a Fairseq checkpoint configuration."""
    cfg = checkpoint.get("cfg")
    if cfg is None:
        raise ValueError("Graphormer checkpoint is missing 'cfg'")

    cfg_values = _config_values(cfg)
    task_values = _config_values(cfg_values.get("task"))
    model_values = _config_values(cfg_values.get("model"))
    if not model_values:
        raise ValueError("Graphormer checkpoint is missing 'cfg.model'")

    saved_values = {**task_values, **model_values}
    values = {name: saved_values[name] for name in _MODEL_ARG_NAMES if name in saved_values}
    missing = sorted(_REQUIRED_MODEL_ARGS - values.keys())
    if missing:
        raise ValueError(f"Graphormer checkpoint is missing model arguments: {', '.join(missing)}")

    values["pretrained_model_name"] = "none"
    values["pretrained_model_path"] = ""
    values["load_pretrained_model_output_layer"] = False
    return argparse.Namespace(**values)


@functools.lru_cache(maxsize=4)
def _load_model(property_name: str) -> Any:
    """Load and cache the Graphormer model for *property_name*.

    Returns the loaded torch model, or raises if the stack/checkpoints are
    unavailable. Cached so the (expensive) load happens once per kernel.
    """
    import torch
    from graphormer.models.graphormer import GraphormerModel

    _ensure_cpu_compiler_on_path()

    if property_name not in REDOX_PROPERTIES:
        raise ValueError(f"unsupported redox property: {property_name}")

    base = checkpoint_dir()
    if base is None:
        raise RuntimeError("GRAPHORMER_CHECKPOINT_DIR is not set or does not exist")

    checkpoint = REDOX_PROPERTIES[property_name]["checkpoint"]
    model_path = os.path.join(base, checkpoint)
    device = _device()

    saved = torch.load(model_path, map_location="cpu")
    if not isinstance(saved, dict) or not isinstance(saved.get("model"), dict):
        raise TypeError(f"Graphormer checkpoint does not contain a model state dict: {model_path}")

    model = GraphormerModel.build_model(_model_args(saved), task=None)
    model.load_state_dict(saved["model"], strict=True)
    model = model.to(device)
    model.eval()
    return model


def _smiles_to_item(smiles: str) -> Any:
    """Convert a SMILES string to a preprocessed Graphormer graph item."""
    import torch
    from graphormer.data.wrapper import preprocess_item
    from ogb.utils.mol import smiles2graph
    from torch_geometric.data import Data

    graph = smiles2graph(smiles)
    graph["edge_index"] = torch.from_numpy(graph["edge_index"]).long()
    graph["edge_attr"] = torch.from_numpy(graph["edge_feat"]).long()
    graph["x"] = torch.from_numpy(graph["node_feat"]).long()
    graph.pop("edge_feat")
    graph.pop("node_feat")
    graph["sname"] = smiles
    graph["gf"] = None
    graph["y"] = torch.tensor(0)
    item = Data(**graph)
    item.idx = 0
    item.y = item.y.reshape(-1)
    return preprocess_item(item)


def run_real_inference(smiles_list: list[str], property_name: str) -> list[dict]:
    """Run Graphormer inference for a batch of SMILES.

    Returns one result dict per input SMILES. Raises on environment/model
    problems.
    """
    import torch
    from fairseq import utils
    from graphormer.data.dataset import BatchedDataDataset

    model = _load_model(property_name)
    device = torch.device(_device())

    # Convert SMILES to graphs, tracking which are valid.
    items: list[Any] = []
    results: list[dict] = []
    valid_indices: list[int] = []
    for index, smiles in enumerate(smiles_list):
        try:
            item = _smiles_to_item(smiles)
        except Exception as exc:  # noqa: BLE001 - per-molecule failure
            item = None
            results.append(
                {
                    "smiles": smiles,
                    "status": "failed",
                    "potential": None,
                    "unit": UNIT,
                    "failure_reason": f"SMILES to graph conversion failed: {exc}",
                }
            )
        else:
            if item["x"] is not None and item["x"].shape[0] > MAX_ATOMS:
                results.append(
                    {
                        "smiles": smiles,
                        "status": "failed",
                        "potential": None,
                        "unit": UNIT,
                        "failure_reason": f"Exceeds max of {MAX_ATOMS} non-H atoms",
                    }
                )
            else:
                valid_indices.append(index)
                results.append(
                    {"smiles": smiles, "status": "succeeded", "potential": None, "unit": UNIT, "failure_reason": None}
                )
        items.append(item)

    if valid_indices:
        batch = BatchedDataDataset(
            None,
            max_node=MAX_ATOMS,
            multi_hop_max_dist=model.args.multi_hop_max_dist,
            spatial_pos_max=model.args.spatial_pos_max,
        )
        sample = batch.collater([items[i] for i in valid_indices])
        sample = utils.move_to_cuda(sample, device=device)
        with torch.no_grad():
            preds = model(sample)[:, 0, :].detach().cpu().numpy()
        preds = [float(p[0]) for p in preds.tolist()]
        for valid_idx, prediction in zip(valid_indices, preds):
            results[valid_idx]["potential"] = round(prediction, 4)

    return results


def validate_inputs(smiles_list: list[str]) -> None:
    """Validate redox-prediction inputs, raising ``ValueError`` on bad input.

    Kept separate from inference so callers (including the thin tool wrappers
    that may dispatch to the sidecar service) can fail fast on bad input without
    touching the model.
    """
    if not isinstance(smiles_list, list) or not smiles_list:
        raise ValueError("smiles_list must be a non-empty list of SMILES strings")
    if len(smiles_list) > MAX_BATCH_SIZE:
        raise ValueError(f"A maximum of {MAX_BATCH_SIZE} SMILES strings is supported per request")


def predict(smiles_list: list[str], property_name: str) -> dict:
    """Predict a redox potential per molecule with the Graphormer model.

    Requires the model stack and checkpoints (``GRAPHORMER_CHECKPOINT_DIR``);
    raises if they are unavailable.
    """
    validate_inputs(smiles_list)
    if property_name not in REDOX_PROPERTIES:
        raise ValueError(f"unsupported redox property: {property_name}")

    return {
        "property_name": property_name,
        "unit": UNIT,
        "num_molecules": len(smiles_list),
        "predictions": run_real_inference(smiles_list, property_name),
    }
