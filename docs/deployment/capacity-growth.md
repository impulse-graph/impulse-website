# Capacity Growth & Scratch Arena Sizing

As new `.imps` snapshot generations grow in cardinality, the engine scales its off-heap `VmQueryContext` scratch arenas without causing Out-of-Memory (OOM) errors or unpredictable latency spikes. The Impulse Graph Engine uses a strict **Monotonic Capacity Rule**: off-heap scratch pool capacities only grow, never shrink, ensuring stability in high-throughput environments.

## The Monotonic Capacity Rule

1. **No Shrinking**: Scratch buffer sizes only increase across snapshot swaps. This prevents thrashing where the engine constantly reallocates and deallocates off-heap memory.
2. **Exact Domain Cardinality Sizing**: Because every `.imps` snapshot encodes the exact node cardinality $N_d$ per domain in its catalog header, intermediate bitsets ($\lceil N_d / 64 \rceil$ words) and state vectors are sized deterministically at snapshot load time.

## GrowthPolicies

When configuring an execution pool across snapshot rotations, a `GrowthPolicy` dictates how off-heap scratch arenas react when a newly swapped `.imps` snapshot exceeds the previous generation's cardinality:

| Policy | Behavior | Best Use Case |
|--------|----------|---------------|
| `FIXED` | Hard limits based on the initial configuration. Exceeding limits throws a `CapacityExceededException`. | Embedded environments, strict memory limits. |
| `GROW_ON_EXCEED` | Automatically expands off-heap scratch arenas by a growth factor (e.g., 1.5x) when a larger snapshot is swapped in. | Long-lived services with A/B snapshot rotation. |
| `SNAPSHOT_ACTUAL` | Sizes strictly to the exact domain cardinalities of the loaded `.imps` snapshot. | Offline analytical pipelines. |

## Headroom Monitoring

The engine exposes JMX and Prometheus metrics to monitor current off-heap scratch capacity headroom:

- `impulse_capacity_nodes_headroom_percent`
- `impulse_capacity_edges_headroom_percent`
