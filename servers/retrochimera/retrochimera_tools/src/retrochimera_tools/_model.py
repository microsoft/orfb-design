# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""In-kernel RetroChimera retrosynthesis planning.

Faithful port of the original standalone FastAPI ``retrochimera`` service's
multi-step planning logic (RetroStar search over a RetroChimera single-step
model, with a bundled purchasable-compound inventory and a single-step fallback),
adapted to run **inside the Agora Workbench kernel** and to return plain
dictionaries instead of pydantic models.

Heavy dependencies (``syntheseus``, ``rdkit``, the ``retrochimera`` model
package) and the model checkpoints are imported / loaded lazily so this module
stays importable during server setup; real planning requires that stack plus
the checkpoints.

Enable real planning by:
  * installing syntheseus + rdkit + the retrochimera package into the kernel,
  * setting ``RETROCHIMERA_CHECKPOINT_DIR`` to the model checkpoints.

The bundled inventory is used by default. Set ``RETROCHIMERA_INVENTORY_PATH``
to override it with another one-SMILES-per-line file.
"""

from __future__ import annotations

import hashlib
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

LOGGER = logging.getLogger(__name__)

# Planning configuration mirrors the original config.yaml.
MAX_NUM_RESULTS = 50
DEFAULT_NUM_RESULTS = 5
MAX_DEPTH = 10
ROUTE_EXTRACTION_TIMEOUT_S = 30.0
DEFAULT_INVENTORY_PATH = Path(__file__).resolve().parent / "data" / "retrochimera_inventory.csv"

# Rule-application worker pool sizing. RetroChimera's ``RuleApplicationServer``
# defaults to ``cpu_count()`` workers (the original standalone endpoint relied on
# this). The ~146k-rule base is *sharded* across the workers (each loads ``1/N``
# of the rules), so going wider does not replicate the base — but each worker is
# still a separate process with its own interpreter/RDKit overhead and a
# concurrent ``get_products`` allocation spike, so total memory does grow with
# N. We therefore keep the library ``cpu_count()`` default (ideal on a
# large-memory host: max parallelism, matches the original) and expose
# ``RETROCHIMERA_NUM_PROCESSES`` as an override so RAM-constrained hosts can dial
# it down (e.g. to 2). When the override is unset we omit the kwarg entirely so
# the library applies its own (cgroup-aware) default.


def _num_processes_override() -> Optional[int]:
    """Return the explicit rule-application worker count, or ``None`` for the
    library default (``cpu_count()``).

    Reads ``RETROCHIMERA_NUM_PROCESSES``; an unset, empty, non-integer, or
    non-positive value means "use the library default".
    """
    raw = os.getenv("RETROCHIMERA_NUM_PROCESSES", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _inventory_path() -> Path:
    raw_path = os.getenv("RETROCHIMERA_INVENTORY_PATH", "").strip()
    path = Path(raw_path).expanduser() if raw_path else DEFAULT_INVENTORY_PATH
    if not path.is_file():
        raise FileNotFoundError(f"RetroChimera inventory file does not exist: {path}")
    return path


def _canonical_inventory_sha256(valid_smiles: list[str]) -> str:
    canonical_contents = "\n".join(sorted(set(valid_smiles))).encode("utf-8")
    return hashlib.sha256(canonical_contents).hexdigest()


@lru_cache(maxsize=1)
def _load_inventory_bundle() -> tuple[Any, str]:
    """Load the inventory and identify the exact canonicalized contents."""
    path = _inventory_path()
    from rdkit import Chem
    from syntheseus.search.mol_inventory import SmilesListInventory

    valid_smiles: list[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            smiles = line.strip()
            if smiles and not smiles.startswith("#"):
                mol = Chem.MolFromSmiles(smiles)
                if mol is not None:
                    valid_smiles.append(Chem.MolToSmiles(mol))
    if not valid_smiles:
        raise ValueError(f"RetroChimera inventory contains no valid SMILES: {path}")
    digest = _canonical_inventory_sha256(valid_smiles)
    return SmilesListInventory(valid_smiles, canonicalize=False), digest


def _load_inventory() -> Any:
    return _load_inventory_bundle()[0]


def _inventory_sha256() -> str:
    return _load_inventory_bundle()[1]


def live_worker_count() -> int:
    """Number of live child processes of this process (rule-application workers)."""
    from multiprocessing import active_children

    return len(active_children())


def _process_rss_mb(pid: Any) -> float:
    with open(f"/proc/{pid}/statm", "r", encoding="utf-8") as handle:
        resident_pages = int(handle.read().split()[1])
    return resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)


def total_rss_mb() -> Optional[float]:
    """Resident memory of this process plus its live workers, in MiB.

    The rule-application workers are separate processes, so the sidecar's own RSS
    says nothing about the memory they hold — the total is the number that matters
    for a recycle threshold. Forked workers share pages copy-on-write, so this
    over-counts somewhat; it is a monitoring signal, not an accounting figure.
    Returns ``None`` where ``/proc`` is unavailable (e.g. non-Linux dev machines).
    """
    from multiprocessing import active_children

    try:
        total = _process_rss_mb("self")
    except (OSError, IndexError, ValueError):
        return None

    for child in active_children():
        try:
            total += _process_rss_mb(child.pid)
        except (OSError, IndexError, ValueError):
            continue  # raced with the worker exiting
    return total


def recycle_rule_application_pools() -> int:
    """Tear down and re-fork the loaded model's rule-application worker pools.

    Defence-in-depth against memory growth *inside* long-lived workers (RDKit
    caches, allocator fragmentation) that no upstream fix would address. Only the
    worker pools are recycled — the multi-GB model checkpoint stays loaded, so this
    costs a rulebase reload rather than a full model reload, and peak memory does
    not spike because the old pool is closed before the new one is started.

    Returns the number of pools recycled.
    """
    model = _load_model()  # cached; does not re-read the checkpoint
    recycled = 0

    for submodel in getattr(model, "_models", []):
        server = getattr(submodel, "_server", None)
        if server is None:
            continue  # not a template-based submodel

        try:
            server.close()
        except Exception:
            LOGGER.exception("Error closing rule application pool for %s", type(submodel).__name__)

        # If this raises, the submodel is left with a closed pool and subsequent
        # planning will fail loudly rather than silently returning wrong results.
        submodel.start_server(rulebase_dir=submodel.model_dir)
        recycled += 1

    return recycled


@lru_cache(maxsize=1)
def _load_model() -> Any:
    """Load the RetroChimera single-step model from the checkpoint directory.

    The rule-application worker pool defaults to the library's ``cpu_count()``;
    set ``RETROCHIMERA_NUM_PROCESSES`` to override it (see
    ``_num_processes_override``). This is a process-global load (via
    ``lru_cache``); when the model runs inside the co-located sidecar service it
    is loaded exactly once per container.
    """
    checkpoint_dir = os.environ["RETROCHIMERA_CHECKPOINT_DIR"]
    from retrochimera import RetroChimeraModel

    kwargs: dict[str, Any] = {}
    override = _num_processes_override()
    if override is not None:
        # ``template_localization`` is the model-subdir name in models.json; the
        # matching kwarg threads down to RuleApplicationServer(num_processes=...).
        # Omitted when unset so the library applies its own cpu_count() default.
        kwargs["template_localization"] = {"num_processes": override}

    return RetroChimeraModel(model_dir=checkpoint_dir, **kwargs)


# --------------------------------------------------------------------------- #
# Route extraction helpers (operate on plain dicts).
# --------------------------------------------------------------------------- #
def _reactant_smiles(reactant: Any) -> str:
    return reactant.smiles if hasattr(reactant, "smiles") else str(reactant)


def _extract_route_from_nodes(route_nodes: Any) -> dict:
    """Build a route dict from syntheseus route nodes (AndNodes carry reactions)."""
    from syntheseus.search.graph.and_or import AndNode

    and_nodes = sorted(
        (node for node in route_nodes if isinstance(node, AndNode)),
        key=lambda n: n.depth,
    )
    steps = []
    for i, and_node in enumerate(and_nodes, start=1):
        reaction = and_node.reaction
        reactants = [{"smiles": _reactant_smiles(r), "is_purchasable": None} for r in reaction.reactants]
        product = reaction.product.smiles if hasattr(reaction.product, "smiles") else str(reaction.product)
        steps.append({"step": i, "reactants": reactants, "product": product})
    return {"reactions": steps, "num_steps": len(steps), "starting_materials_in_catalog": None}


def _single_step_fallback(smiles: str, num_results: int, model: Any) -> list[dict]:
    """Single-step retrosynthesis fallback when multi-step planning fails."""
    from syntheseus import Molecule

    predictions = model([Molecule(smiles)], num_results=num_results)
    routes = []
    for pred in predictions[0]:
        reactants = [{"smiles": _reactant_smiles(r), "is_purchasable": None} for r in pred.reactants]
        routes.append(
            {
                "reactions": [{"step": 1, "reactants": reactants, "product": smiles}],
                "num_steps": 1,
                "starting_materials_in_catalog": None,
            }
        )
    return routes


def _annotate_routes_with_purchasability(routes: list[dict], inventory: Any) -> list[dict]:
    """Mark each route's leaf reactants (starting materials) as purchasable or not."""
    if inventory is None:
        return routes
    from syntheseus import Molecule

    annotated = []
    for route in routes:
        products_in_route = {step["product"] for step in route["reactions"]}
        all_leaves_purchasable = True
        annotated_reactions = []
        for step in route["reactions"]:
            annotated_reactants = []
            for reactant in step["reactants"]:
                smiles_str = reactant["smiles"]
                if smiles_str not in products_in_route:  # leaf / starting material
                    try:
                        purchasable = inventory.is_purchasable(Molecule(smiles_str))
                    except Exception:  # noqa: BLE001 - third-party inventory failures mean unavailable
                        purchasable = False
                    if not purchasable:
                        all_leaves_purchasable = False
                    annotated_reactants.append({"smiles": smiles_str, "is_purchasable": purchasable})
                else:  # intermediate
                    annotated_reactants.append({"smiles": smiles_str, "is_purchasable": None})
            annotated_reactions.append(
                {"step": step["step"], "reactants": annotated_reactants, "product": step["product"]}
            )
        annotated.append(
            {
                "reactions": annotated_reactions,
                "num_steps": route["num_steps"],
                "starting_materials_in_catalog": all_leaves_purchasable,
            }
        )
    return annotated


def _run_real_retrosynthesis(smiles: str, num_results: int) -> dict:
    """Run RetroStar multi-step planning for one target."""
    from collections.abc import Sequence

    from syntheseus import Molecule
    from syntheseus.search.algorithms.best_first.retro_star import RetroStarSearch
    from syntheseus.search.analysis.route_extraction import iter_routes_cost_order
    from syntheseus.search.graph.and_or import AndNode
    from syntheseus.search.node_evaluation.base import NoCacheNodeEvaluator
    from syntheseus.search.node_evaluation.common import ConstantNodeEvaluator

    inventory = _load_inventory()
    model = _load_model()

    class UnitReactionCost(NoCacheNodeEvaluator[AndNode]):
        def _evaluate_nodes(self, nodes: Sequence[AndNode], graph=None) -> list[float]:
            return [1.0 for _ in nodes]

    target_mol = Molecule(smiles)
    message: Optional[str] = None

    if inventory.is_purchasable(target_mol):
        return {
            "status": 200,
            "attempts": 1,
            "routes": [],
            "route_source": "inventory_match",
            "inventory_sha256": _inventory_sha256(),
            "all_routes_resolved": None,
            "message": "Target molecule found as purchasable in inventory",
        }

    search = RetroStarSearch(
        reaction_model=model,
        mol_inventory=inventory,
        value_function=ConstantNodeEvaluator(constant=0.0),
        and_node_cost_fn=UnitReactionCost(),
        limit_iterations=num_results * 10,
    )

    routes: list[dict] = []
    route_source = "multi_step"
    try:
        graph, _output = search.run_from_mol(target_mol)
        try:
            for route_nodes in iter_routes_cost_order(
                graph, max_routes=num_results, max_time_s=ROUTE_EXTRACTION_TIMEOUT_S
            ):
                route = _extract_route_from_nodes(route_nodes)
                if route["reactions"]:
                    routes.append(route)
        except Exception:  # noqa: BLE001 - extraction failure falls back to the single-step model
            routes = []
        if not routes:
            routes = _single_step_fallback(smiles, num_results, model)
            route_source = "single_step_fallback"
    except Exception:  # noqa: BLE001 - search failure falls back to the single-step model
        routes = _single_step_fallback(smiles, num_results, model)
        route_source = "single_step_fallback"

    routes = _annotate_routes_with_purchasability(routes, inventory)
    all_resolved = all(r["starting_materials_in_catalog"] for r in routes) if routes else None
    return {
        "status": 200,
        "attempts": 1,
        "routes": routes,
        "route_source": route_source,
        "inventory_sha256": _inventory_sha256(),
        "all_routes_resolved": all_resolved,
        "message": message,
    }


def validate_inputs(smiles: str, num_results: int = DEFAULT_NUM_RESULTS) -> None:
    """Validate retrosynthesis inputs, raising ``ValueError`` on bad input.

    Kept separate from planning so callers (including the thin tool wrapper that
    may dispatch to the sidecar service) can fail fast on bad input without
    touching the model.
    """
    if not isinstance(smiles, str) or not smiles.strip():
        raise ValueError("smiles must be a non-empty SMILES string")
    if not isinstance(num_results, int) or not (1 <= num_results <= MAX_NUM_RESULTS):
        raise ValueError(f"num_results must be an int in [1, {MAX_NUM_RESULTS}]")


def predict_retrosynthesis(smiles: str, num_results: int = DEFAULT_NUM_RESULTS) -> dict:
    """Plan retrosynthetic routes for a target molecule.

    Args:
        smiles: SMILES string of the target molecule.
        num_results: Number of routes to return (1–50).

    Returns:
        A dict with ``status``, ``attempts``, ``routes`` (each a dict of
        ``reactions``/``num_steps``/``starting_materials_in_catalog``),
        ``all_routes_resolved`` and ``message``. Requires the RetroChimera model
        stack and checkpoints; raises if they are unavailable.
    """
    validate_inputs(smiles, num_results)
    return _run_real_retrosynthesis(smiles, num_results)
