# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import hashlib
import os
import subprocess
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_SCRIPT = REPO_ROOT / "scripts" / "fetch_checkpoints.sh"


def _checkpoint_fixture(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "retrochimera_pistachio.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("checkpoint/models.json", "{}\n")
        handle.writestr("checkpoint/smiles_transformer/combined.ckpt", "smiles\n")
        handle.writestr("checkpoint/template_localization/combined.ckpt", "template\n")
    return archive, hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest()


def _fixture_env(tmp_path: Path, archive: Path, checksum: str) -> dict[str, str]:
    return {
        **os.environ,
        "ORFB_MODEL_ASSETS_DIR": str(tmp_path / "assets"),
        "ORFB_CHECKPOINT_CACHE_DIR": str(tmp_path / "cache"),
        "RETROCHIMERA_CHECKPOINT_URL": archive.as_uri(),
        "RETROCHIMERA_CHECKPOINT_MD5": checksum,
    }


def _graphormer_fixture_env(tmp_path: Path, reduction: Path, oxidation: Path) -> dict[str, str]:
    env = {
        **os.environ,
        "ORFB_MODEL_ASSETS_DIR": str(tmp_path / "assets"),
        "ORFB_CHECKPOINT_CACHE_DIR": str(tmp_path / "cache"),
        "GRAPHORMER_REDUCTION_CHECKPOINT_URL": reduction.as_uri(),
        "GRAPHORMER_OXIDATION_CHECKPOINT_URL": oxidation.as_uri(),
        "GRAPHORMER_REDUCTION_CHECKPOINT_SHA256": hashlib.sha256(reduction.read_bytes()).hexdigest(),
        "GRAPHORMER_OXIDATION_CHECKPOINT_SHA256": hashlib.sha256(oxidation.read_bytes()).hexdigest(),
    }
    env.pop("GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE", None)
    env.pop("GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE", None)
    return env


def test_fetch_graphormer_checkpoints_from_local_paths(tmp_path):
    reduction = tmp_path / "reduction.pt"
    oxidation = tmp_path / "oxidation.pt"
    reduction.write_bytes(b"reduction checkpoint")
    oxidation.write_bytes(b"oxidation checkpoint")
    env = {
        **os.environ,
        "ORFB_MODEL_ASSETS_DIR": str(tmp_path / "assets"),
        "ORFB_CHECKPOINT_CACHE_DIR": str(tmp_path / "cache"),
        "GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE": str(reduction),
        "GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE": str(oxidation),
    }

    first = subprocess.run(
        [FETCH_SCRIPT, "graphormer"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    model_dir = tmp_path / "assets" / "graphormer"

    assert "pinned Hugging Face release" in first.stdout
    assert (model_dir / "reduction_checkpoint_best.pt").read_bytes() == reduction.read_bytes()
    assert (model_dir / "oxidation_checkpoint_best.pt").read_bytes() == oxidation.read_bytes()

    second = subprocess.run(
        [FETCH_SCRIPT, "graphormer"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert second.stdout.count("already staged") == 2

    oxidation.write_bytes(b"Oxidation checkpoint")
    third = subprocess.run(
        [FETCH_SCRIPT, "graphormer"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "copying oxidation checkpoint" in third.stdout
    assert (model_dir / "oxidation_checkpoint_best.pt").read_bytes() == oxidation.read_bytes()


def test_fetch_graphormer_checkpoints_from_hugging_face(tmp_path):
    reduction = tmp_path / "graphormer_reduction.pt"
    oxidation = tmp_path / "graphormer_oxidation.pt"
    reduction.write_bytes(b"hosted reduction checkpoint")
    oxidation.write_bytes(b"hosted oxidation checkpoint")
    env = _graphormer_fixture_env(tmp_path, reduction, oxidation)

    first = subprocess.run(
        [FETCH_SCRIPT, "graphormer"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    model_dir = tmp_path / "assets" / "graphormer"
    cache_dir = tmp_path / "cache"

    assert "pinned Hugging Face release" in first.stdout
    assert (model_dir / "reduction_checkpoint_best.pt").read_bytes() == reduction.read_bytes()
    assert (model_dir / "oxidation_checkpoint_best.pt").read_bytes() == oxidation.read_bytes()
    assert (cache_dir / reduction.name).read_bytes() == reduction.read_bytes()
    assert (cache_dir / oxidation.name).read_bytes() == oxidation.read_bytes()

    second = subprocess.run(
        [FETCH_SCRIPT, "graphormer"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert second.stdout.count("already staged, checksum verified") == 2


def test_fetch_graphormer_checkpoints_reject_bad_checksum(tmp_path):
    reduction = tmp_path / "graphormer_reduction.pt"
    oxidation = tmp_path / "graphormer_oxidation.pt"
    reduction.write_bytes(b"hosted reduction checkpoint")
    oxidation.write_bytes(b"hosted oxidation checkpoint")
    env = _graphormer_fixture_env(tmp_path, reduction, oxidation)
    env["GRAPHORMER_REDUCTION_CHECKPOINT_SHA256"] = "0" * 64

    result = subprocess.run(
        [FETCH_SCRIPT, "graphormer"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert not (tmp_path / "assets" / "graphormer" / "reduction_checkpoint_best.pt").exists()


def test_make_groups_graphormer_checkpoint_targets(tmp_path):
    reduction = tmp_path / "reduction_checkpoint_best.pt"
    oxidation = tmp_path / "oxidation_checkpoint_best.pt"

    result = subprocess.run(
        [
            "make",
            "--dry-run",
            "--jobs=2",
            f"GRAPHORMER_REDUCTION_CKPT={reduction}",
            f"GRAPHORMER_OXIDATION_CKPT={oxidation}",
            str(reduction),
            str(oxidation),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.count("scripts/fetch_checkpoints.sh graphormer") == 1


def test_fetch_retrochimera_checkpoint(tmp_path):
    archive, checksum = _checkpoint_fixture(tmp_path)
    env = _fixture_env(tmp_path, archive, checksum)

    first = subprocess.run(
        [FETCH_SCRIPT, "retrochimera"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    model_dir = tmp_path / "assets" / "retrochimera" / "pistachio"

    assert "public Figshare release" in first.stdout
    assert (model_dir / "models.json").is_file()
    assert (model_dir / "smiles_transformer" / "combined.ckpt").is_file()
    assert (model_dir / "template_localization" / "combined.ckpt").is_file()
    assert f"md5={checksum}" in (model_dir / "checkpoint-source.txt").read_text()

    second = subprocess.run(
        [FETCH_SCRIPT, "retrochimera"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "already unpacked" in second.stdout


def test_fetch_retrochimera_checkpoint_rejects_bad_checksum(tmp_path):
    archive, _checksum = _checkpoint_fixture(tmp_path)
    env = _fixture_env(tmp_path, archive, "0" * 32)

    result = subprocess.run(
        [FETCH_SCRIPT, "retrochimera"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert not (tmp_path / "assets" / "retrochimera" / "pistachio").exists()


def test_fetch_checkpoints_rejects_unknown_component():
    result = subprocess.run(
        [FETCH_SCRIPT, "unknown"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "all|graphormer|retrochimera" in result.stderr
