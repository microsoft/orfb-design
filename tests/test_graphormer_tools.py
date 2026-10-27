# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""Tests for Graphormer redox validation, checkpoint loading, and inference."""

import argparse
import contextlib
import sys
import types

import pytest
from graphormer_tools import _model
from graphormer_tools.redox import predict_oxidation_potential, predict_reduction_potential


def test_reduction_batch_limit():
    with pytest.raises(ValueError):
        predict_reduction_potential(["CCO"] * 33)


def test_reduction_empty_input():
    with pytest.raises(ValueError):
        predict_reduction_potential([])


def test_oxidation_batch_limit():
    with pytest.raises(ValueError):
        predict_oxidation_potential(["CCO"] * 33)


def test_oxidation_empty_input():
    with pytest.raises(ValueError):
        predict_oxidation_potential([])


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_redox_proxies_to_service(monkeypatch):
    """When the sidecar URL is set, the wrapper POSTs and returns its JSON."""
    import json
    import urllib.request

    captured = {}
    expected = {"property_name": "reduction", "predictions": []}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(json.dumps(expected).encode("utf-8"))

    monkeypatch.setenv("GRAPHORMER_MODEL_SERVICE_URL", "http://127.0.0.1:8902")
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = predict_reduction_potential(["CCO", "c1ccccc1"])

    assert {key: result[key] for key in expected} == expected
    assert set(result) == set(expected) | {"provenance"}
    assert result["provenance"]["model_artifact"] == "reduction_checkpoint_best.pt"
    assert result["provenance"]["applicability"] == "not_assessed"
    assert captured["url"] == "http://127.0.0.1:8902/predict"
    assert captured["body"] == {"smiles_list": ["CCO", "c1ccccc1"], "property_name": "reduction"}


def test_redox_validation_runs_before_service(monkeypatch):
    """Bad input raises ValueError client-side, without touching the service."""
    import urllib.request

    def fail(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("service should not be called on invalid input")

    monkeypatch.setenv("GRAPHORMER_MODEL_SERVICE_URL", "http://127.0.0.1:8902")
    monkeypatch.setattr(urllib.request, "urlopen", fail)

    with pytest.raises(ValueError):
        predict_oxidation_potential([])


def test_model_args_merge_saved_config_and_disable_pretraining():
    checkpoint = {
        "cfg": {
            "task": {"num_classes": 1, "multi_hop_max_dist": 5},
            "model": argparse.Namespace(
                encoder_layers=12,
                encoder_embed_dim=768,
                encoder_ffn_embed_dim=768,
                encoder_attention_heads=32,
                max_nodes=128,
                num_atoms=4608,
                num_edges=1536,
                num_in_degree=512,
                num_out_degree=512,
                num_spatial=512,
                num_edge_dis=128,
                edge_type="multi_hop",
                spatial_pos_max=1024,
                pretrained_model_name="pcqm4mv2_graphormer_base",
                pretrained_model_path="/training/host/checkpoint.pt",
                save_dir="/training/host/checkpoints",
            ),
        }
    }

    args = _model._model_args(checkpoint)

    assert args.num_classes == 1
    assert args.encoder_layers == 12
    assert args.pretrained_model_name == "none"
    assert args.pretrained_model_path == ""
    assert args.load_pretrained_model_output_layer is False
    assert not hasattr(args, "save_dir")


def test_load_model_reconstructs_and_strict_loads_state_dict(tmp_path, monkeypatch):
    model_path = tmp_path / "reduction_checkpoint_best.pt"
    model_path.write_bytes(b"fixture")
    state = {"encoder.weight": object()}
    checkpoint = {
        "cfg": {
            "task": {"num_classes": 1},
            "model": argparse.Namespace(
                encoder_layers=12,
                encoder_embed_dim=768,
                encoder_ffn_embed_dim=768,
                encoder_attention_heads=32,
                max_nodes=128,
                num_atoms=4608,
                num_edges=1536,
                num_in_degree=512,
                num_out_degree=512,
                num_spatial=512,
                num_edge_dis=128,
                edge_type="multi_hop",
                multi_hop_max_dist=5,
                spatial_pos_max=1024,
                pretrained_model_name="pcqm4mv2_graphormer_base",
                pretrained_model_path="/training/host/checkpoint.pt",
            ),
        },
        "model": state,
    }
    captured = {}

    class FakeModel:
        def __init__(self, args):
            self.args = args

        def load_state_dict(self, loaded, strict):
            captured["state"] = loaded
            captured["strict"] = strict

        def to(self, device):
            captured["device"] = device
            return self

        def eval(self):
            captured["eval"] = True
            return self

    class FakeGraphormerModel:
        @classmethod
        def build_model(cls, args, task):
            captured["args"] = args
            captured["task"] = task
            return FakeModel(args)

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    fake_torch.load = lambda path, map_location: checkpoint
    graphormer_module = types.ModuleType("graphormer")
    models_module = types.ModuleType("graphormer.models")
    model_module = types.ModuleType("graphormer.models.graphormer")
    model_module.GraphormerModel = FakeGraphormerModel

    monkeypatch.setenv("GRAPHORMER_CHECKPOINT_DIR", str(tmp_path))
    monkeypatch.setenv("GRAPHORMER_DEVICE", "cpu")
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "graphormer", graphormer_module)
    monkeypatch.setitem(sys.modules, "graphormer.models", models_module)
    monkeypatch.setitem(sys.modules, "graphormer.models.graphormer", model_module)
    monkeypatch.setattr(_model, "_ensure_cpu_compiler_on_path", lambda: None)
    _model._load_model.cache_clear()

    loaded = _model._load_model("reduction")

    assert loaded.args.pretrained_model_name == "none"
    assert loaded.args.pretrained_model_path == ""
    assert captured == {
        "args": loaded.args,
        "task": None,
        "state": state,
        "strict": True,
        "device": "cpu",
        "eval": True,
    }
    _model._load_model.cache_clear()


def test_inference_uses_raw_checkpoint_outputs(monkeypatch):
    class FakeX:
        shape = (3, 1)

    class FakePredictions:
        def __getitem__(self, key):
            assert key == (slice(None), 0, slice(None))
            return self

        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self

        def tolist(self):
            return [[-2.75], [1.5]]

    class FakeModel:
        args = types.SimpleNamespace(multi_hop_max_dist=5, spatial_pos_max=1024)

        def __call__(self, sample):
            assert len(sample) == 2
            assert all(item["x"].shape == (3, 1) for item in sample)
            return FakePredictions()

    class FakeBatch:
        def __init__(self, dataset, **kwargs):
            assert dataset is None
            assert kwargs == {
                "max_node": _model.MAX_ATOMS,
                "multi_hop_max_dist": 5,
                "spatial_pos_max": 1024,
            }

        def collater(self, items):
            return items

    fake_torch = types.ModuleType("torch")
    fake_torch.device = lambda value: value
    fake_torch.no_grad = contextlib.nullcontext
    fairseq_module = types.ModuleType("fairseq")
    fairseq_module.utils = types.SimpleNamespace(move_to_cuda=lambda sample, device: sample)
    graphormer_data = types.ModuleType("graphormer.data")
    graphormer_dataset = types.ModuleType("graphormer.data.dataset")
    graphormer_dataset.BatchedDataDataset = FakeBatch

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "fairseq", fairseq_module)
    monkeypatch.setitem(sys.modules, "graphormer.data", graphormer_data)
    monkeypatch.setitem(sys.modules, "graphormer.data.dataset", graphormer_dataset)
    monkeypatch.setattr(_model, "_load_model", lambda property_name: FakeModel())
    monkeypatch.setattr(_model, "_device", lambda: "cpu")
    monkeypatch.setattr(_model, "_smiles_to_item", lambda smiles: {"x": FakeX()})

    predictions = _model.run_real_inference(["CCO", "O"], "reduction")

    assert [item["potential"] for item in predictions] == [-2.75, 1.5]
