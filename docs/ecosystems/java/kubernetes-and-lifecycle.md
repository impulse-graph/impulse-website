# Day-2 Operations: Kubernetes, Hot-Swap Lifecycle & Schema Evolution

!!! info "Version Note: v0.11 Tooling Suite"
    `SnapshotLifecycleManager`, `SnapshotResolver`, `LocalPathSnapshotResolver`, `ConsumerSchemaContext`, `SwapResult`, `SnapshotContractValidator`, and lifecycle-backed `ImpulseHealthIndicator` probes (`startup()`, `readiness()`, `liveness()`) ship in **`v0.11`** (`0.11.0`). Low-level `SnapshotSwapManager` and `GraphSnapshot`-backed `ImpulseHealthIndicator` are available in `0.10.1`.

Because Impulse Graph executes read-only traversals directly over immutable `.imps` files, production microservices never apply row-by-row mutations in place. Instead, an upstream job periodically writes a fresh `.imps` snapshot to object storage (S3/GCS) or a mounted volume, and stateless serving pods atomically rotate epochs in memory with zero query downtime (see [Long-Lived Dynamic Service](../../deployment/dynamic-service.md)).

This guide covers wiring transactional Blue/Green swaps, Kubernetes probes, rolling schema evolution, and `cgroups v2` container memory limits in Java.

---

## 1. Zero-Downtime Hot-Swap with `SnapshotLifecycleManager`

`SnapshotLifecycleManager<S>` (`org.impulsegraph.vm.lifecycle`) wraps `SnapshotSwapManager` with a transactional 5-stage validation pipeline before any live traffic sees a new snapshot:

1. **Isolated Staging (`Arena.ofShared()`)**: Maps the candidate `.imps` file into an isolated candidate `Arena` and verifies Page 0 magic, section bounds, and the trailing SHA-256 checksum (`verifyChecksum = true`).
2. **Consumer Contract Validation (`SnapshotContractValidator`)**: Verifies every required domain, relation, endpoint, traversal direction (`CSC`), attribute type, vector dimension, and nullability invariant against the service's compiled `GraphManifest`, producing pre-resolved `BoundSchemaHandles`.
3. **Optional Pre-Swap Query Binding (`QueryRegistry`)**: Compiles and binds all registered `openCypher` / `ImpScheme` queries against the candidate snapshot inside the candidate `Arena`.
4. **Typed Facade Construction**: Instantiates the AOT-generated `<Graph>Snapshot` facade (or exposes `GraphSnapshot` directly).
5. **Atomic Swap & Virtual-Thread RCU Drain**: Atomically flips the active epoch pointer. A background virtual thread parks until all in-flight readers on the retired epoch release their leases (`activeReaders == 0`), then unmaps the retired `Arena` and optionally deletes the staged local file.

### Complete Production Service Example

```java
package com.example.bank.service;

import com.example.bank.graph.AccountAttrs;
import com.example.bank.graph.BankGraphSnapshot;
import org.impulsegraph.api.lifecycle.CandidateSnapshotRef;
import org.impulsegraph.api.lifecycle.ConsumerSchemaContext;
import org.impulsegraph.api.lifecycle.SnapshotResolver;
import org.impulsegraph.api.lifecycle.SwapResult;
import org.impulsegraph.compiler.registry.QueryRegistry;
import org.impulsegraph.storage.csr.ImpulseHealthIndicator;
import org.impulsegraph.storage.lifecycle.LocalPathSnapshotResolver;
import org.impulsegraph.vm.lifecycle.SnapshotLifecycleManager;

import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public final class BankGraphService implements AutoCloseable {

    private final SnapshotResolver resolver;
    private final SnapshotLifecycleManager<BankGraphSnapshot> lifecycle;
    private final ImpulseHealthIndicator healthIndicator;
    private final ScheduledExecutorService poller;

    public BankGraphService(Path snapshotPath, QueryRegistry queryRegistry) {
        // Detect file updates by SHA-256 digest (or RevisionMode.METADATA for mtime+size)
        this.resolver = new LocalPathSnapshotResolver(
                snapshotPath,
                LocalPathSnapshotResolver.RevisionMode.SHA256,
                false // deleteOnRejectOrClose: set true when staging temp files from S3/GCS
        );

        // Create lifecycle manager bound to BankGraphSnapshot.SCHEMA + pre-swap query gate
        this.lifecycle = BankGraphSnapshot.createLifecycleManager(
                resolver,
                epoch -> queryRegistry.validateAndBindAll(epoch.graph(), epoch.arena())
        );

        this.healthIndicator = lifecycle.healthIndicator();

        // Poll every 30 seconds on a background scheduler
        this.poller = Executors.newSingleThreadScheduledExecutor(Thread.ofPlatform().daemon().factory());
        this.poller.scheduleWithFixedDelay(this::refreshSnapshot, 30, 30, TimeUnit.SECONDS);
    }

    /** Reader hot path: acquires a lock-free epoch lease and releases it in finally. */
    public List<Long> findHighBalanceAccounts(UUID userKey, double minBalance) {
        return lifecycle.withSnapshot(snap ->
                snap.users()
                        .fromKey(userKey)
                        .outOwns()
                        .where(AccountAttrs.BALANCE.ge(minBalance))
                        .toKeyList()
        );
    }

    /** Background refresh loop with exhaustive sealed SwapResult handling. */
    void refreshSnapshot() {
        SwapResult<BankGraphSnapshot> result = lifecycle.pollAndSwap(resolver);
        switch (result) {
            case SwapResult.Swapped<BankGraphSnapshot> s ->
                    System.out.printf("Swapped active graph epoch to revision %s%n", s.revisionId());
            case SwapResult.Unchanged<BankGraphSnapshot> _ -> {
                // No new revision available; no-op
            }
            case SwapResult.Rejected<BankGraphSnapshot> r ->
                    System.err.printf("Rejected candidate %s (%d violation(s)): %s%n",
                            r.candidateRevisionId(), r.violations().size(), r.message());
        }
    }

    public ImpulseHealthIndicator health() {
        return healthIndicator;
    }

    @Override
    public void close() {
        poller.shutdownNow();
        lifecycle.close();
    }
}
```

### Custom S3 / GCS `SnapshotResolver` SPI

For cloud object stores, implement the single-method `@FunctionalInterface` `SnapshotResolver`. Pass `deleteOnRejectOrClose = true` on `CandidateSnapshotRef` so `SnapshotLifecycleManager` automatically deletes rejected candidates immediately and deletes retired local `.imps` files once their epoch drains:

```java
SnapshotResolver s3Resolver = (ConsumerSchemaContext ctx) -> {
    // Query S3/GCS manifest pointer for major schema version (e.g., s3://bucket/BankGraph/v1/latest.json)
    String latestEtag = fetchLatestEtag(ctx.graphName(), ctx.majorVersion());
    if (ctx.activeSnapshotRevision().filter(latestEtag::equals).isPresent()) {
        return java.util.Optional.empty(); // Already serving latest revision
    }
    Path stagedFile = downloadToLocalNvmeScratch(latestEtag);
    return java.util.Optional.of(new CandidateSnapshotRef(latestEtag, stagedFile, true));
};
```

### What Happens When a Corrupt or Incompatible Snapshot Lands?

If a truncated upload, SHA-256 mismatch, or schema-breaking `.imps` file is discovered during `pollAndSwap`:

1. `trySwap` catches the `IOException` or `SnapshotCompatibilityException` **before** touching the active pointer.
2. The candidate `Arena` (`arenaB`) is closed immediately, and `stagedFile` is deleted if `deleteOnRejectOrClose == true`.
3. `swapRejectedCount` increments (`ImpulseMetricsRegistry` records `snapshotSwapRejected`), `swapDegraded` flips to `true`, and `SwapResult.Rejected` returns structured `CompatibilityViolation` diagnostics.
4. **Zero Reader Impact**: The existing healthy epoch continues serving 100% of queries without latency spikes or restarts.

---

## 2. Kubernetes Probes (`startupProbe`, `readinessProbe`, `livenessProbe`)

`ImpulseHealthIndicator` (zero external framework imports) exposes three distinct probe methods tailored to Kubernetes pod semantics:

| Probe Method | Before Initial Mount | Active Epoch Healthy | Active Healthy + Candidate Swap Rejected (`swapDegraded=true`) | Purpose in Kubernetes |
| :--- | :---: | :---: | :---: | :--- |
| **`health.startup()`** | `DOWN` (503) | `UP` (200) | `UP` (200) | Gives the pod time to download the initial `.imps` from S3/GCS and run `mmap` + `MADV_WILLNEED` warmup without triggering `livenessProbe` kills. |
| **`health.readiness()`** | `DOWN` (503) | `UP` (200) | **`UP` (200)** | Keeps the pod in Service endpoints when a bad upstream snapshot is rejected—because the prior valid epoch is still serving traffic! |
| **`health.liveness()`** | `UP` (200) | `UP` (200) | **`UP` (200)** | Prevents cascading fleet-wide pod restart storms if S3 is unreachable or an upstream build breaks compatibility. |

### Wiring to Spring Boot Actuator or Lightweight HTTP Endpoints

```java
import org.impulsegraph.storage.csr.ImpulseHealthIndicator;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("impulseGraph")
public class ImpulseSpringHealthIndicator implements HealthIndicator {

    private final ImpulseHealthIndicator delegate;

    public ImpulseSpringHealthIndicator(BankGraphService service) {
        this.delegate = service.health();
    }

    @Override
    public Health health() {
        ImpulseHealthIndicator.HealthReport report = delegate.readiness();
        Health.Builder builder = (report.status() == ImpulseHealthIndicator.Status.UP)
                ? Health.up()
                : Health.down();
        report.details().forEach(builder::withDetail);
        return builder.build();
    }
}
```

 Expose dedicated `/healthz/startup`, `/healthz/ready`, and `/healthz/live` handlers mapped to `delegate.startup()`, `delegate.readiness()`, and `delegate.liveness()`, and configure your Kubernetes `Deployment`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bank-graph-service
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: app
          image: ghcr.io/example/bank-graph-service:1.2.0
          env:
            - name: JAVA_TOOL_OPTIONS
              value: >-
                --add-modules jdk.incubator.vector
                --enable-native-access=ALL-UNNAMED
                -Xms2g -Xmx4g
                -XX:+UseZGC -XX:+ZGenerational
          resources:
            requests:
              cpu: "2"
              memory: "16Gi"
            limits:
              memory: "16Gi"
          startupProbe:
            httpGet:
              path: /healthz/startup
              port: 8080
            periodSeconds: 5
            failureThreshold: 36   # Up to 180s for cold S3 download + mmap warmup
          readinessProbe:
            httpGet:
              path: /healthz/ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /healthz/live
              port: 8080
            periodSeconds: 15
            failureThreshold: 3
```

Alert on `swapDegraded == true` (or `swapRejectedCount > 0` in Prometheus / JMX `ImpulseEngineMXBean`) rather than failing `livenessProbe`.

---

## 3. Rolling Zero-Downtime Schema Evolution (`Expand -> Migrate -> Contract`)

`SnapshotContractValidator` and `impulse-j schema check-compat` enforce **consumer-driven structural subtyping**: a producer snapshot is valid for a consumer if and only if it provides at least the domains, relations, directions, and attribute contracts required by that consumer's `GraphManifest`.

| Producer Change | Classification | Runtime & CI Behavior |
| :--- | :---: | :--- |
| Add a new Domain, Relation, or Attribute | **Safe (Additive)** | Existing consumer pods ignore unknown catalog entries and hot-swap cleanly. |
| Add `CSC` (`in` direction) to an `[out]`-only relation | **Safe (Additive)** | Consumers requiring `[out]` continue walking CSR; new consumers can walk `[in]`. |
| Narrow attribute from `nullable: true` to `nullable: false` | **Safe (Covariant)** | Consumers expecting `nullable: true` accept non-null snapshot columns. |
| Remove a required Domain, Relation, or Attribute | **Breaking** | Rejected with `MISSING_DOMAIN`, `MISSING_RELATION`, or `MISSING_ATTRIBUTE`. |
| Change attribute type or vector dimension (`float32[128]` → `float32[256]`) | **Breaking** | Rejected with `TYPE_MISMATCH` or `DIMENSION_MISMATCH`. |
| Widen attribute from `nullable: false` to `nullable: true` | **Breaking** | Rejected with `NULLABILITY_MISMATCH` (prevents silent `0`/`""` reads on primitive getters). |
| Drop `CSC` on a relation where consumer declares `directions: [out, in]` | **Breaking** | Rejected with `MISSING_DIRECTION`. |

### Three-Step Zero-Downtime Rollout Pattern

To rename or replace an attribute (e.g., migrating `legacy_tier` to `kyc_tier`) without coordinating downtime between producer pipelines and Kubernetes deployments:

1. **Expand (Producer)**: Add `kyc_tier` alongside `legacy_tier` in the producer build. Run `impulse-j schema check-compat` against active v1 consumer schemas—all pass because `legacy_tier` is still present. Old pods hot-swap to the expanded snapshot seamlessly.
2. **Migrate (Consumers)**: Roll out v2 consumer pods whose `schema.yaml` requires `kyc_tier` and drops `legacy_tier` from its required contract (or marks `kyc_tier` `optional: true, since: "1.2.0"` if v2 code must deploy before the producer runs!).
3. **Contract (Producer)**: Once no v1 consumer pods remain active, remove `legacy_tier` from the producer manifest and update the CI `check-compat` consumer registry.

---

## 4. Kubernetes Memory Sizing & Avoiding the `cgroups v2` `mmap` `OOMKilled` Trap

Understanding how the JVM and Linux `cgroups v2` account for memory-mapped `.imps` files is essential when setting Kubernetes `resources.limits.memory`:

1. **JVM Heap (`-Xmx`) & `-XX:MaxDirectMemorySize` Are Untouched**: `BinarySnapshotLoader` mounts `.imps` files via `FileChannel.map(FileChannel.MapMode.READ_ONLY, ...)`. Mapped segments consume **zero bytes** of Java heap (`-Xmx`) and are **not** counted against `-XX:MaxDirectMemorySize`.
2. **Linux `cgroups v2` Counts Resident Page Cache Toward `limits.memory`**: When query threads touch `.imps` pages (or `segment.load()` issues `MADV_WILLNEED`), the Linux kernel faults those 4KB pages into the OS page cache. Under `cgroups v2`, resident file-backed pages (`file` in `/sys/fs/cgroup/memory.stat`) count directly toward the container's `memory.max` (`resources.limits.memory`) alongside anonymous memory (`anon`).

!!! warning "The High-`-Xmx` `OOMKilled` Anti-Pattern"
    Developers accustomed to heap-based caches often set `-Xmx14g` inside a `16Gi` container. Because JVM heap (`anon` memory) **cannot** be evicted to disk when Kubernetes disables swap, a `14Gi` heap + `1Gi` Metaspace/CodeCache/stacks leaves almost zero room in `memory.max` for the page cache or temporary native arenas—triggering a kernel `OOMKilled` (`exitCode: 137`)!

### Why Clean `READ_ONLY` `mmap` Pages Are Safe When `-Xmx` Is Lean

Because `.imps` segments are mapped strictly **`READ_ONLY`**, every faulted snapshot page in the OS page cache is **clean** (unmodified relative to the backing file on NVMe/EBS/ephemeral storage).

When container memory approaches `limits.memory`—including during a **Blue/Green hot-swap** while Epoch A is draining and Epoch B is warming up—the Linux kernel's `cgroups v2` page reclaimer seamlessly evicts cold clean `file` pages without invoking the OOM killer, **as long as non-reclaimable anonymous memory stays well below `limits.memory`**.

### Recommended Pod Memory Sizing Formula

$$\text{Pod } \texttt{limits.memory} \;\ge\; \underbrace{\texttt{-Xmx}}_{\text{2–4 GiB}} \;+\; \underbrace{\text{JVM Non-Heap \& Query Pools}}_{\text{1–2 GiB}} \;+\; \underbrace{\text{Hot Working Set of } \texttt{.imps}}_{\text{1.0x Snapshot Size (or hot slice)}}$$

* **Keep `-Xmx` Small (`2Gi–4Gi`)**: With `ImpulseVM` and AOT `RowView` cursors allocating zero hot-path objects, `-Xmx` only serves HTTP/gRPC request/response DTOs.
* **Set `requests.memory == limits.memory` (`Guaranteed` QoS)**: Prevents node-level memory pressure from preempting serving pods first.
* **S3/GCS Staging Storage**: Mount an NVMe-backed `emptyDir` volume (not `emptyDir: { medium: Memory }` / `tmpfs`!) for local `.imps` staging. Never store `.imps` files on `tmpfs`, because `tmpfs` pages are accounted as non-evictable `shmem`/`anon` memory rather than reclaimable disk-backed page cache!

For deeper JVM flag, Transparent Huge Pages, and `VmQueryContext` pool tuning, see **[Memory & Performance Tuning](../../deployment/memory-tuning.md)** and **[Capacity Growth](../../deployment/capacity-growth.md)**.
