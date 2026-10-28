# Server network

ORFB Design runs six containers: five scientific domain servers and one router.
An agent normally connects only to `orfb-hub`; the hub forwards execution to
the appropriate domain while preserving each server's isolated environment and
session state.

| Server | Host port | Primary role | External model asset |
|---|---:|---|---|
| [`orfb-hub`](hub.md) | 8050 | Unified MCP entry point | None |
| [`orfb`](orfb.md) | 8040 | Molecular characterization | None |
| [`graphormer`](graphormer.md) | 8041 | Redox-potential prediction | Reduction and oxidation checkpoints |
| [`retrochimera`](retrochimera.md) | 8042 | Retrosynthesis planning | Pistachio-trained model |
| [`soltrannet`](soltrannet.md) | 8043 | Aqueous-solubility prediction | None; weights ship with the package |
| [`ezbattery`](ezbattery.md) | 8044 | Cell simulation | None |

## Shared server pattern

Each domain server is an Agora Workbench `CodeExecutionServer` and exposes:

- an `execute_<domain>_code` MCP tool backed by a persistent Python kernel;
- domain functions that are injected into that kernel;
- tool metadata for search and workflow planning;
- an agent skill describing safe and effective use of the domain; and
- session, artifact, and job-management utilities supplied by Agora Workbench.

The domain functions are called from Python inside the execution tool. They are
not separate network services that an agent must wire together manually.

## Cross-server work

The servers share an object-transfer topology. A kernel can send Python objects
to another domain without serializing large intermediate results through the
agent conversation. For example, an ORFB characterization session can send a
candidate list to Graphormer or RetroChimera.

The hub's state graph is the union of the five domain state graphs. It does not
impose a single fixed campaign pipeline; agents can choose the domain order
appropriate to the screening objective.

## Security boundary

The default Compose deployment uses no-op authentication and binds published
ports to `127.0.0.1`. Access to an execution endpoint is effectively
code-execution access inside that server's container. Keep the endpoints
loopback-only unless you add production authentication and network controls.
