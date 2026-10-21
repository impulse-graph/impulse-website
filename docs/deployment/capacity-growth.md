# Capacity Growth & Headroom Management

As your graph grows, the engine needs to scale internal memory buffers without causing Out-of-Memory (OOM) errors or unpredictable latency spikes. The Impulse Graph Engine uses a strict **Monotonic Capacity Rule**: capacities can only grow, never shrink, ensuring stability in high-throughput environments.

## The Monotonic Capacity Rule

1. **No Shrinking**: Buffer sizes only increase. This prevents thrashing where the engine constantly reallocates and deallocates memory.
2. **Delta Node ID Fence**: Newly added nodes during a live session are assigned IDs above a specific threshold (fence), keeping the base snapshot array domains cleanly separated from the live delta domain.

## GrowthPolicies

When constructing an `ImpulseGraph` instance, you configure a `GrowthPolicy` that dictates how the engine reacts when capacity bounds are exceeded.

| Policy | Behavior | Best Use Case |
|--------|----------|---------------|
| `FIXED` | Hard limits based on the provided configuration. Exceeding limits throws a `CapacityExceededException`. | Embedded environments, strict memory limits. |
| `GROW_ON_EXCEED` | Automatically expands memory mapping sizes or heap buffers by a growth factor (e.g., 1.5x) when full. | General dynamic services (most common). |
| `SNAPSHOT_ACTUAL` | Sizes strictly to the exact requirements of the loaded base snapshot, disallowing live delta growth. | Offline analytical pipelines. |

=== "Java"
    ```java
    ImpulseGraph liveGraph = ImpulseGraph.builder(snapshotPath)
        .withGrowthPolicy(GrowthPolicy.GROW_ON_EXCEED)
        .withGrowthFactor(1.5f)
        .build();
    ```

## `pool.adaptTo()`

In environments where you want manual control over growth, or when you proactively know a massive ingestion spike is coming, you can instruct the engine to adapt its resource pools immediately.

=== "Java"
    ```java
    CapacityLimits upcomingDemand = CapacityLimits.builder()
        .maxNodes(EntityType.USER, 150_000_000)
        .maxEdges(Relation.USER_TO_GROUP, 800_000_000)
        .build();

    // Proactively resize buffers before the ingestion spike hits
    liveGraph.pool().adaptTo(upcomingDemand);
    ```

## Headroom Monitoring

The engine exposes JMX and Prometheus metrics to monitor current capacity headroom.
- `impulse_capacity_nodes_headroom_percent`
- `impulse_capacity_edges_headroom_percent`

Alerting on these metrics allows you to trigger manual compactions or preemptive pool adaptations before `GROW_ON_EXCEED` causes momentary allocation latency.
