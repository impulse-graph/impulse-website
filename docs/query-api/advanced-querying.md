# State Projections, Reducers & Loops

While pure reachability queries pass a boolean BitSet from domain to domain, analytical queries often need to **repeat walks until convergence** or **carry and aggregate computed state** (costs, distances, capacities, or path witnesses) across hops.

---

## 1. Fixed-Point & Bounded Loops (`repeatUntilStable` & `repeat`)

For recursive hierarchies, supply chains, power-grid islanding, or Relationship-Based Access Control (ReBAC), Impulse Graph executes multi-hop loops directly in off-heap bitset registers with zero per-iteration heap allocations:

### 1.1 Unbounded Transitive Closure (`repeatUntilStable`)
Repeatedly steps across the specified relation until no new nodes are discovered ($\text{Frontier}_{t+1} == \text{Frontier}_t$), with optional inline CEL edge/node filtering:

```java
var groups = snap.domain("Group");

// Compute full reflexive transitive closure (R*, >= 0 hops) of parent groups
List<String> allAncestorGroups = groups.fromKey("grp_engineering_west")
    .repeatUntilStable("PARENT_GROUP")
    .toKeyList();

// Transitive closure with an inline CEL predicate
List<String> activeAncestors = groups.fromKey("grp_engineering_west")
    .repeatUntilStable("PARENT_GROUP", "edge.active == true")
    .toKeyList();
```

!!! important
    **Reflexive Closure ($R^*$) vs. Positive Closure ($R^+$) for Cycle Detection**:
    In `ImpOpsBytecodeEmitter`, `repeatUntilStable(relation)` initializes the accumulator register (`R2`) with the starting seed frontier (`R0`), computing the **reflexive** transitive closure ($R^*$, which includes 0-hop starting nodes). When testing whether a node can reach *itself* via a cycle ($\ge 1$ hop), step one hop first with `.out(relation)` before calling `.repeatUntilStable(relation)`:
    ```java
    boolean hasCycle = snap.domain("Account")
        .from(suspectId)
        .out("TRANSFERRED_TO")
        .repeatUntilStable("TRANSFERRED_TO")
        .toBitSet()
        .get(suspectId);
    ```

### 1.2 Bounded Hop Expansion (`repeat(n, relation)`)
Applies a domain-preserving relation step up to $N$ hops:

```java
// Expand up to 3 hops across the KNOWS relation
Set<Long> threeHopNetwork = snap.domain("User")
    .fromKey("usr_alice")
    .repeat(3, "KNOWS")
    .toSet();
```

---

## 2. State-Bearing Traversals & Monoidic Reducers (`.outWithState`)

When a query carries computed state across an edge relation $R: D_1 \to D_2$, multiple edges from $D_1$ will frequently land on the same destination node in $D_2$.

Instead of emitting duplicate rows (like a SQL `JOIN`), `.outWithState(relation, stateProjections)` (and `.outWithState(relation, edgePredicate, stateProjections)`) requires an explicit **monoidic reducer** specifying how converging values are collapsed into a single value per target node:

```text
state.<target_field>:<REDUCER> = <CEL Expression>
```

```java
List<String> budgetCities = snap.domain("City").fromKey("ATL")
    .outWithState("FLIGHT_LEG", "state.min_cost:MIN = src.airport_fee + edge.ticket_price")
    .filter("state.min_cost <= 350.0")
    .toKeyList();
```

### 2.1 The 10 Hardware SIMD Reducers & Co-Reducers

`org.impulsegraph.api.traversal.Reducer` defines 8 core monoidic reducers and 2 witness co-reducers:

| Reducer Tag | Category | Monoid Operation | Hardware / SIMD Execution Strategy |
| :--- | :--- | :--- | :--- |
| **`:MIN`** | Math | Minimum ($\min$) | Conflict-aware SIMD vector minimum prior to target scatter. |
| **`:MAX`** | Math | Maximum ($\max$) | Conflict-aware SIMD vector maximum prior to target scatter. |
| **`:SUM`** | Math | Accumulation ($+$) | Vectorized histogram accumulation / scatter-add. |
| **`:AVG`** | Math | Arithmetic Mean | Dual accumulators (`SUM` + `COUNT`) $\to$ final vector division. |
| **`:COUNT`** | Topology | Path Multiplicity | Vectorized arrival counter per target node. |
| **`:OR`** | Logic | Boolean Union ($\lor$) | Bitwise `OR` across 64-bit / 512-bit words. |
| **`:AND`** | Logic | Universal Match ($\land$)| Bitwise `AND` across 64-bit / 512-bit words. |
| **`:ANY`** | Witness | Arbitrary Witness | Masked vector scatter using inverted visited bitmask. |
| **`:ARGMIN(f)`**| Co-Reducer | Min-Value Witness | Reuses the SIMD lane-winner mask from field `f`'s `:MIN` reduction. |
| **`:ARGMAX(f)`**| Co-Reducer | Max-Value Witness | Reuses the SIMD lane-winner mask from field `f`'s `:MAX` reduction. |

!!! note
    **Semantic Type Safety on Node IDs**: Even though Dense IDs are integers (`0..N-1`), the compiler tracks them as `TYPE_NODE_ID` and forbids nonsensical arithmetic reducers (`:SUM`, `:AVG`) on node IDs while permitting witness reducers (`:ANY`, `:MIN`, `:MAX`, `:ARGMIN`, `:ARGMAX`).

### 2.2 Witness Extraction with Co-Reducers (`:ARGMIN` / `:ARGMAX`)
When computing a `:MIN` or `:MAX` metric (such as the lowest shipping cost to each distribution center), you often want to know **which source node produced that winning value**. `:ARGMIN(state.field)` and `:ARGMAX(state.field)` update the witness atomically alongside the winning metric:

```java
List<String> qualifyingCenters = snap.domain("Warehouse").from(activeWarehouses)
    .outWithState("TRUCK_ROUTE", """
        state.lowest_cost:MIN = src.handling_cost + edge.freight_fee,
        state.best_warehouse:ARGMIN(state.lowest_cost) = src.id
        """)
    .filter("state.lowest_cost <= 500.0")
    .toKeyList();
```

### 2.3 In-Domain State Projections (`.project`)
To compute derived state values across the currently active domain *without* walking an edge ($\langle D, S \rangle \to \langle D, S' \rangle$), use `.project(...)`:

```java
snap.domain("Player").fromKey("player_42")
    .outWithState("PLAYED_IN", """
        state.total_hits:SUM = edge.hits,
        state.total_at_bats:SUM = edge.at_bats
        """)
    .project("state.batting_avg = state.total_hits / max(1.0, state.total_at_bats)")
    .filter("state.batting_avg >= 0.300")
    .toKeyList();
```

### 2.4 Consuming & Extracting Projected State at the Terminal Step

There are three ways projected state and numeric attributes are consumed at the end of a query pipeline:

1. **Downstream Frontier Filtering (`Traversal<T>`)**:
   As shown above, any `state.<field>` computed by `.outWithState(...)` or `.project(...)` can be referenced in subsequent `.filter("state.<field> ...")` or `.outWithState(...)` steps to prune the active node frontier before calling `.toBitSet()`, `.toList()`, `.toKeyList()`, or `.count()`.
2. **Terminal Scalar & Witness Reductions (`ImpulseQueryBuilder` & `ImpulseGraphQuery`)**:
   When you want to reduce projected values across the surviving target frontier into a single scalar aggregate (`Double`) or extract the winning target node ID (`Integer`), `org.impulsegraph.api.ImpulseQueryBuilder` provides terminal reduction operators (`reduceMin()`, `reduceMax()`, `reduceSum()`, `reduceAvg()`, `reduceArgMin()`, `reduceArgMax()`):
   ```java
   import org.impulsegraph.api.ArgType;
   import org.impulsegraph.api.ImpulseGraphQuery;
   import org.impulsegraph.api.ImpulseQueryBuilder;

   // Terminal scalar reduction (OP_REDUCE / OP_VECTOR_REDUCE_SUM -> Double)
   ImpulseGraphQuery<Double> minCostQuery = new ImpulseQueryBuilder<Double>()
       .input("Warehouse", ArgType.SINGLE_NODE)
       .walkEdge("TRUCK_ROUTE")
       .projectExpression("handling_cost", "+", "freight_fee")
       .reduceMin();
   double minCost = minCostQuery.execute(snap, startWarehouseId);

   // Terminal witness reduction (reduceArgMin / reduceArgMax -> winning target Node ID)
   ImpulseGraphQuery<Integer> bestCenterQuery = new ImpulseQueryBuilder<Integer>()
       .input("Warehouse", ArgType.SINGLE_NODE)
       .walkEdge("TRUCK_ROUTE")
       .projectExpression("handling_cost", "+", "freight_fee")
       .reduceArgMin();
   int bestCenterId = bestCenterQuery.execute(snap, startWarehouseId);
   ```
3. **Multi-Column Tabular State Extraction (`v1.0.0` Roadmap)**:
   On the high-level `Traversal<T>` fluent interface, terminal collectors (`collect()`, `toBitSet()`, `toList()`, `toKeyList()`, `count()`) currently return the surviving target node frontier (`ImpulseBitSet` / dense IDs / keys). Direct multi-column tabular extraction of attached `state.*` registers (`Traversal.collectRows()`) is scheduled for the `v1.0.0` release.

---

## 3. Early Scalar State vs. Late Materialization of Heavy Attributes

A key rule of thumb for high-throughput queries is distinguishing lightweight scalar state from heavy strings or high-dimensional vectors:

* **Carry Lightweight Numbers in State (`float32`, `int32`, `float64`)**: Accumulating weights, distances, or timestamps inside `.outWithState(...)` keeps all data in contiguous SIMD vector registers.
* **Late-Materialize Strings & Business Keys at the End**: Never copy strings during intermediate hops. Traverse strictly over dense `0..N-1` IDs and resolve external keys or string attributes only for the surviving target nodes via `.toKeyList()`:

```java
// Hot loop walks User -> Product -> Factory strictly on dense integer IDs,
// resolving string business keys only for the surviving Factory nodes at the end:
List<String> factoryKeys = snap.domain("User")
    .fromKey("usr_alice")
    .out("PURCHASED", "edge.amount >= 100.0")
    .out("MANUFACTURED_BY")
    .toKeyList();
```

---

## 4. Multi-Lane Bit-Sliced Traversals, Quorum & Outage Screening (Planned v0.9.1)

Standard 1-bit frontiers (`TYPE_BITSET_HANDLE` `0x04`) collapse all seed nodes into a single boolean union ($\bigcup_i \text{Reach}(s_i)$), erasing per-seed provenance after the first hop. **Multi-Lane Bit-Sliced Execution (`TYPE_LANE_FRONTIER = 0x10`, opcodes `0xC0..0xC9`)** generalizes the frontier into an adaptive $W$-bit unsigned word per node (`WIDTH_8` $\le 8$, `WIDTH_16` $\le 16$, `WIDTH_32` $\le 32$, `WIDTH_64` $\le 64$ lanes, with automatic $\lceil K / 64 \rceil$ multi-batch chunking for $K > 64$), propagating up to 64 independent traversals in a single CSR/CSC pass.

### 4.1 The Five Multi-Lane Pipeline Stages (`0xC0..0xC9`)

1. **Three Initialization Modes (`0xC0..0xC2`)**:
   * **Distinct Seeds (`OP_LANE_INIT_SEEDS` `0xC0` / `.fromSeeds(...)` / `.fromKeys(...)`)**: Assigns each seed $s_b$ to its own bit lane (`lanes[s_b] |= (1ULL << b)`).
   * **Concept Groups (`OP_LANE_INIT_GROUPS` `0xC1` / `.fromGroups(...)`)**: Maps multiple candidate nodes $(u, g)$ into shared group lane $g \in [0, K-1]$ (`lanes[u] |= (1ULL << g)`) for Group Steiner Tree discovery.
   * **Counterfactual Edge Outages (`OP_LANE_SET_EDGE_MASK` `0xC2` / `.fromOutages(...)`)**: Attaches per-edge trip bitmasks (`edge_trip_mask[rel_id][e] |= (1ULL << b)`) so lane $b$ treats branch $e$ as open/tripped during $N-1$ / $N-2$ contingency screening.
2. **Single-Pass Bit-Sliced CSR/CSC Walks (`OP_LANE_CSR_WALK` `0xC3`, `OP_LANE_CSC_WALK` `0xC4`)**:
   * Propagates all active lanes across outgoing (`0xC3`) or incoming (`0xC4`) edges in a single topology scan:
     $$\text{next\_lanes}[v] \;\mathrel{\vert}=\; (\text{current\_lanes}[u] \land \text{active\_mask}) \land \neg\text{edge\_trip\_mask}[\text{rel\_id}][e]$$
   * Setting the `FIXPOINT` modifier (`flags & 0x04` / `.repeatUntilStable(rel)`) executes delta-frontier propagation (`newly_reached = step_out[v] & ~out_lanes[v]`) until all lanes converge with zero per-iteration allocations.
3. **Bit-Lane Pruning (`OP_LANE_PRUNE_MASK` `0xC5`)**:
   * **`mode = 0` (Explicit Deny Mask / `.pruneWhere` / `.pruneDeniedBy`)**: Clears denied nodes or strips specific lane bits via `lanes[u] &= ~deny_mask[u]`.
   * **`mode = 1` (Intra-Word `ALLOW & ~DENY` Zanzibar Split)**: Splits the lane word into `allow_bits = low_half` and `deny_bits = high_half`, computing `lanes[u] = allow_bits & ~deny_bits` in one register operation.
   * **`mode = 2` (Degree-Gated Hub Quorum Prune / `.pruneHubs(maxDeg, minQuorum)`)**: Suppresses promiscuous supernode hubs by zeroing `lanes[u]` whenever $\text{deg}(u) > \text{max\_deg}$ and $\text{popcount}(\text{lanes}[u]) < \text{min\_quorum}$.
4. **Quorum Filtering & Bridging Back to 1-Bit `Traversal` (`OP_LANE_FILTER_QUORUM` `0xC6`)**:
   * Evaluates $\text{popcount}(\text{lanes}[u] \land \text{req\_mask}) \ge \text{min\_k} \land (\text{lanes}[u] \land \text{forbid\_mask}) = 0$ and emits a standard `TYPE_BITSET_HANDLE` (`0x04`) via `.toQuorumTraversal(minLanes)`.
5. **Terminal Per-Lane Reductions & Minimum Set Cover (`0xC7..0xC9`)**:
   * **`OP_LANE_REDUCE_AND` (`0xC7` / `.checkAllNodesReachedPerLane()`)**: Bitwise AND across all $N_d$ nodes to identify which contingency lanes maintained full connectivity (`active_mask & ~all_reached`).
   * **`OP_LANE_REDUCE_ATTR` (`0xC8` / `.reducePerLane(...)` / `.argMinNodesPerLane(...)`)**: Single-pass reduction of a scalar attribute into $K$ per-lane accumulators (`SUM`, `MIN`, `MAX`, `COUNT`, or deterministic lowest-ID-tie-broken `ARGMIN` / `ARGMAX` witness node IDs).
   * **`OP_LANE_SET_COVER` (`0xC9` / `.findSetCoverPairs(...)` / `.findGreedySetCover(...)`)**: Finds exact 2-node pairs or a greedy minimum witness node cover (`argmax_u popcount(lanes[u] & uncovered)`) spanning `target_mask`.

```cpp
#include "impulse_vm_fluent.hpp"

using namespace impulse::vm;
SnapshotView snap(raw_snapshot);

// Evaluate a 10-gene oncology panel (8 tumor drivers + 2 cardiac safety genes) in one 16-bit pass:
MultiLaneResult panel = snap.domain("Gene").multiLane()
    .fromKeys({"BRCA1", "BRCA2", "EGFR", "MYC", "KRAS", "PIK3CA", "BRAF", "ERBB2",
               "KCNH2_SAFE", "SCN5A_SAFE"})
    .out("INTERACTS_GiG")
    .pruneHubs(/*max_degree=*/ 500, /*min_quorum=*/ 2)
    .in("BINDS_CbG")
    .mustHitAtLeast(5, {"BRCA1", "BRCA2", "EGFR", "MYC", "KRAS", "PIK3CA", "BRAF", "ERBB2"})
    .mustAvoidAll({"KCNH2_SAFE", "SCN5A_SAFE"})
    .collect();

auto multi_target_drugs = panel.keysWithQuorum(5);
auto two_drug_cocktails = panel.findSetCoverPairs(0x00FFULL);
```

### 4.2 Empirical Width-Scaling Throughput (`MultiLaneVmBenchmarkTest`, Java 25 VM)

Executed on Apple Silicon (ARM64, JDK 25.0.2) over an off-heap CSR graph with $|V| = 50,000$ nodes and $|E| = 500,000$ directed edges (`org.impulsegraph.vm.MultiLaneVmBenchmarkTest`), a 2-hop accumulated `OP_LANE_CSR_WALK` (`0xC3`) scales near-linearly with the number of active lanes because the CSR offset/target memory reads are amortized across all $L$ bit-lanes:

| Active Lanes ($L$) | Selected `LaneWidth` | 2-Hop Batch Latency | Amortized Latency / Lane | Effective Throughput (Lane-MTEPS) |
| :---: | :---: | :---: | :---: | :---: |
| **`L = 1`** | `WIDTH_8` | `0.224 ms` | `224.26 µs` | `2,229.5 MTEPS` |
| **`L = 8`** | `WIDTH_8` | `0.226 ms` | `28.23 µs` | `17,714.1 MTEPS` |
| **`L = 16`** | `WIDTH_16` | `0.234 ms` | `14.59 µs` | `34,258.8 MTEPS` |
| **`L = 32`** | `WIDTH_32` | `0.225 ms` | `7.04 µs` | `71,012.5 MTEPS` |
| **`L = 64`** | `WIDTH_64` | **`0.230 ms`** | **`3.60 µs`** | **`138,979.4 MTEPS`** |

In the companion N-64 transmission line contingency benchmark (`OP_LANE_SET_EDGE_MASK` `0xC2` + 3-hop `OP_LANE_CSR_WALK` `0xC3` + `OP_LANE_REDUCE_AND` `0xC7`), screening 64 simultaneous edge outages completes in **`0.411 ms`** (**`6.43 µs` per N-1 outage**, or **`155,576` outages/sec** on a single core).

---

## 5. Hybrid Vector ANN Search & Exact SIMD Reranking (Planned v0.9.1)

For GraphRAG, biomedical knowledge graphs, and semantic entity retrieval, Impulse embeds **Single-Layer Vamana / DiskANN Proximity Graphs (`IMP_INDEX_VAMANA_ANN = 0x08`)** directly into Section 2.6 of the `.imps` file so vector search and symbolic CSR/CSC graph walks share the **exact same $0 \dots N_d-1$ dense domain node IDs** with zero ID translation:

1. **Two-Stage Quantized Vamana Beam Routing (`IMP_INDEX_VAMANA_ANN = 0x08`)**:
   * During greedy beam expansion from `medoid_node_id`, `OP_VECTOR_ANN_SEARCH` (`0xCA`) evaluates compressed routing codes (`BQ1` 1-bit binary via `XOR + popcount`, `SQ8` 8-bit scalar quantization, or `FP16` half-precision) stored in the 128-byte-aligned `quant_slab`, reducing memory bandwidth by `4x–32x`, and then reranks the `ef_search` beam candidates against the full-precision `FLOAT32` attribute column.
2. **Fused `TYPE_LANE_FRONTIER` Handshake (`OP_VECTOR_ANN_SEARCH` `0xCA` with `flags = 1`)**:
   * When `flags & 1 != 0` (or via `MultiLaneBuilder::fromConceptVectors`), `OP_VECTOR_ANN_SEARCH` directly seeds the top-$K$ ANN hits into a `TYPE_LANE_FRONTIER` (`0x10`) without materializing an intermediate host array.
3. **Multi-Hop Graph Walk, Quorum Bridge & Exact SIMD Reranking (`OP_VECTOR_RERANK_DOT` `0xCB`)**:
   * After expanding the vector seeds across symbolic graph relations (`OP_LANE_CSR_WALK` `0xC3`), pruning high-degree hubs (`OP_LANE_PRUNE_MASK` `0xC5`), and filtering for multi-concept bridge nodes (`OP_LANE_FILTER_QUORUM` `0xC6`), `OP_VECTOR_RERANK_DOT` (`0xCB`) computes exact hardware-SIMD similarity (`L2`, `COSINE`, `DOT`) over the 128-byte-aligned `FLOAT32` SoA vector attribute for only the surviving frontier nodes.

```cpp
#include "impulse_vm_fluent.hpp"

using namespace impulse::vm;
SnapshotView snap(raw_snapshot);

// 1. Single-lane Vamana ANN seed -> 2-hop graph expansion -> exact SIMD vector reranking:
std::vector<uint64_t> ranked_compounds = snap.domain("Disease")
    .vectorSearch("disease_embedding_vamana", query_embedding, /*top_k=*/ 16)
    .out("ASSOCIATES_DaG")
    .in("BINDS_CbG")
    .rerank(compound_target_embedding, "compound_embedding", /*metric=COSINE*/ 1)
    .collect();

// 2. Multi-concept Vector + Group Steiner Tree extraction for GraphRAG:
SteinerSubgraph rag_subgraph = snap.domain("Entity").multiLane()
    .fromConceptVectors(
        "entity_embedding_vamana",
        {
            {"GLP1_Agonist", glp1_embedding},
            {"mTOR_Pathway", mtor_embedding},
            {"Diabetic_Nephropathy", nephropathy_embedding}
        },
        /*hits_per_concept=*/ 20
    )
    .out("RELATES_TO")
    .pruneHubs(/*max_degree=*/ 1000, /*min_quorum=*/ 2)
    .out("RELATES_TO")
    .toSteinerSubgraph(/*min_concept_quorum=*/ 2);
```
