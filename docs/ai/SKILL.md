---
name: impulse-graph
description: Architectural rules, engine-native Kleisli set traversal idioms, per-domain dense ID invariants, JVM/Python/C-ABI configuration, and CLI verification commands for the Impulse Graph Engine (.imps). Activate whenever writing, reviewing, or debugging code, schemas, or pipelines using Impulse Graph.
---

# Impulse Graph Engine — AI Coding Agent Skill & Rules (`impulse-graph`)

Follow these seven architectural invariants whenever generating code, queries, schemas, build configurations, or deployment manifests for **Impulse Graph Engine** (`org.impulsegraph` / `impulse-graph`).

---

## 1. What Impulse Graph Is (and Isn't)

* **Immutable Binary Snapshot Engine (`.imps`)**: Impulse Graph pairs a 4KB-page-aligned, 128-byte-section-aligned read-only binary file format (`.imps`) mapped via `mmap` with a 64-register bytecode Virtual Machine (`ImpulseVM` executing `impOps`). It is the **Apache Arrow / Parquet equivalent for Graph Analytics**—not a mutable OLTP row-store graph database.
* **NEVER Generate In-Place Graph Mutations**: Do **not** generate Neo4j/SQL mutation statements (`CREATE`, `MERGE`, `INSERT`, `SET`, `DELETE`, `DETACH DELETE`) or invent `graph.addNode()` / `graph.addEdge()` runtime mutation calls on a loaded `ImpulseGraphSnapshot` / `Snapshot`.
* **Rebuild + Atomic Blue/Green Swap**: Data updates compile a fresh `.imps` file out-of-band (`impulse-graph build` or Java `SnapshotBuilder`) and rotate it into live reader processes with zero lock contention via `SnapshotLifecycleManager` (`v0.11`) or `SnapshotSwapManager` (`impulse-storage`).

---

## 2. Strict Per-Domain Dense ID Independence (`0 .. N_d - 1`)

* **No Global Node ID Space**: Every node domain (`User`, `Account`, `Product`, `Gene`) owns an independent `0`-indexed contiguous dense integer space `0 .. N_d - 1` (`uint16`, `uint32`, or `uint64`). Dense ID `0` in `User` is completely distinct from Dense ID `0` in `Account`.
* **Always Anchor Traversals to an Explicit Domain**: Start every query from an explicit domain view (`snap.domain("User")` in Java/Python/C++, or AOT-generated `bankSnap.users()` in Java `v0.11`). Never pass unanchored raw integer IDs across domains.
* **Never Persist Ephemeral Dense IDs Externally**: Dense IDs (`0 .. N_d - 1`) are internal per-snapshot coordinates that intentionally permute when snapshots are rebuilt or optimized (`--rcm`, `--vamana-locality`). Always resolve external business keys (`UUID`, `String`, `int64`) at query boundaries via `fromKey(...)` / `fromKeys(...)` and materialize results via `toKeyList()` / `toKeySet()`.

---

## 3. 100% Engine-Native Kleisli Set Traversals (Zero Imperative Loops)

* **NEVER Write Client-Side Point-Lookup Loops**: Do **not** iterate over node IDs in application `for` loops (`for (long id : frontier)` in Java or `for u in nodes:` in Python) calling single-node neighbor lookups or manual attribute checks hop-by-hop. That treats the engine as a dumb key-value table and destroys SIMD vectorization and cache locality.
* **Single Pipeline Execution**: Express multi-hop walks (`.out(...)`, `.in(...)`), attribute filters (`.filter("node.age >= 21")` or typed AOT predicates), state projections (`.project(...)`), monoidic aggregations (`Reducer.SUM`, `MIN`, `MAX`, `.outWithState("REL", "state.total:SUM = edge.amount")`), and unbounded transitive closures (`.repeatUntilStable("PARENT_GROUP")`) inside **one engine pipeline** or **one prepared query** (`openCypher`, `ImpLog`, `ImpK`, `ImpScheme`).
* **Honest Capability Reporting**: If an application requires stateful per-path backtracking or an operator not supported by `ImpulseVM`, state that explicitly rather than fabricating client-side imperative traversal loops.

```java
// WRONG — Client-side imperative N+1 point-lookup loop (NEVER DO THIS):
Set<String> flagged = new HashSet<>();
for (long accId : snap.domain("User").fromKey(userId).out("OWNS").toList()) {
    for (long dstId : snap.domain("Account").from(accId).out("TRANSFERRED_TO").toList()) {
        flagged.add(snap.domain("Account").toKey(dstId));
    }
}

// CORRECT — Single engine-native Kleisli set traversal:
List<String> flagged = snap.domain("User")
    .fromKey(userId)
    .out("OWNS")
    .out("TRANSFERRED_TO", "edge.amount >= 10000.0")
    .filter("node.risk_score >= 80")
    .toKeyList();
```

---

## 4. Set Semantics (Not Multi-Set Path Bags)

* **Frontier Compression**: Every step $\langle D, \text{Frontier}, \text{State} \rangle \xrightarrow{R} \langle D', \text{Frontier}', \text{State}' \rangle$ collapses converging incoming edges onto a per-domain `BitSet` (and optional monoid-reduced state vector `SUM` / `MIN` / `MAX` / `ARGMIN` / `ARGMAX`), or a bit-sliced `VmLaneFrontier` (`0xC0`..`0xC9`, up to 64 parallel lanes).
* **No Path Explosion**: Queries never materialize $O(d^k)$ path bags in heap memory, and terminal collectors (`toBitSet()`, `toKeyList()`, `count()`) emit results strictly from the **final active target domain**.

---

## 5. Idiomatic Java Enterprise Configuration (`impulse-graph-java`)

* **Prefer Schema-First AOT Codegen (`v0.11`)**: Define graph contracts in `.imps.schema.yaml` and generate zero-dependency typed wrappers (`<Graph>Snapshot`, `<Domain>Id`, `<Domain>Traversal`, `<Domain>Attrs`, flyweight `<Domain>RowView`) via `org.impulsegraph:impulse-maven-plugin` (`generate` goal) or `impulse-j codegen`.
* **Use `impulse-bom`**: Import `org.impulsegraph:impulse-bom` (`0.11.0` for full AOT/CLI suite; `0.10.1` for core Maven Central runtime artifacts `impulse-api`, `impulse-storage`, `impulse-vm`, `impulse-compiler`, `impulse-builder`). Core runtime modules have **zero third-party dependencies**.
* **Mandatory JDK Compiler & Runtime Flags**:
    * **JDK 22+ / JDK 25 LTS (Recommended)**:
        * `javac`: `--release 25 --add-modules jdk.incubator.vector` (do **not** pass `--enable-native-access` to `javac`).
        * `java` / Surefire / Failsafe: `--add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED`.
    * **JDK 21 LTS**: Add `--enable-preview` to **both** `javac` (`--release 21 --enable-preview --add-modules jdk.incubator.vector`) and `java` (FFM `Arena`/`MemorySegment` is preview in JDK 21 JEP 442).
* **Container & Kubernetes Memory Sizing**: `.imps` files reside off-heap in the OS `mmap` page cache (counted against container `cgroups v2` memory limits, **not** `-Xmx` or `-XX:MaxDirectMemorySize`). Size the JVM heap lean (`-Xms2g -Xmx4g -XX:+UseZGC -XX:+ZGenerational`) and leave container memory headroom for mapped `.imps` pages. Use `Arena.ofShared()` for concurrent multi-threaded snapshots.

---

## 6. Idiomatic Python, PyTorch & Native C-ABI Usage

* **Build Snapshots via Official Tooling Only**: Never write ad-hoc Python/C++/shell byte-packing scripts to create `.imps` files. Always compile CSV/TSV/Parquet datasets with `impulse-graph build --manifest manifest.json -o graph.imps` (or `SnapshotBuilder` / `SnapshotWriter` / `impulse_writer_t`). Enable `"include_csc": true` on relations that will be traversed in reverse (`.in(...)` / `.in_(...)` / `<-[]-`).
* **Python & Multi-Worker PyTorch (`impulse-graph`)**:
    * Open snapshots with `with Snapshot("graph.imps") as snap:` (`pip install impulse-graph==0.10.1`).
    * Anchor traversals via `snap.domain("User").from_key("...").out("...").to_key_list()` or `snap.cypher(query, params={...})`.
    * Access CSR and SoA tensors zero-copy via `snap.get_row_offsets_array(rel_idx)`, `snap.get_col_indices_array(rel_idx)`, `snap.get_attribute_array(rel_idx, attr_idx, dtype=np.float32, shape=...)`, and `snap.sample_neighbors(...)`.
    * In `multiprocessing` or PyTorch `DataLoader(num_workers > 0)`, pass only the `.imps` **file path string** to workers and instantiate `Snapshot(path)` lazily inside each worker so all processes share one read-only OS page-cache mapping (`0 bytes` CoW duplication).
* **Native C / C++20 / Rust (`impulse-cpp` & `impulse-rust`)**:
    * Use caller-allocated prepared statements (`impulse_stmt_prepare` $\to$ `impulse_stmt_buffer_size` $\to$ `impulse_stmt_execute` $\to$ `impulse_stmt_finalize`) for zero-`malloc` execution, C++20 `impulse::vm::SnapshotView` (`impulse_vm_fluent.hpp`), or Rust `impulse_graph::reader::SnapshotReader`.

---

## 7. Self-Verification via Structured JSON CLI Output

Whenever creating, modifying, or debugging `.imps` snapshots, manifests, or `.imps.schema.yaml` contracts, verify your work using machine-readable CLI checks before finishing:

```bash
# 1. Inspect domains, relations, attribute types, and 128B section offsets as JSON
impulse-graph snapshot inspect graph.imps --format json

# 2. Validate 128-byte alignment, CRC-16 header, CSR/CSC transpose invariants, and SHA-256
impulse-graph snapshot validate graph.imps --strict-alignment --deep-audit

# 3. Profile degree skew and high-degree supernodes (Z-score >= 3.0)
impulse-graph snapshot stats graph.imps --supernode-threshold 3.0 --format json

# 4. Pure-Java schema conformance & consumer-driven compatibility gates (impulse-j, v0.11)
impulse-j schema validate src/main/resources/schema.yaml --snapshot graph.imps --format json
impulse-j schema check-compat --snapshot candidate.imps --consumer schema.yaml --format json
```
