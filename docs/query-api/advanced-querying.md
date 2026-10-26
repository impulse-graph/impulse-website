# State Projections, Reducers & Loops

While pure reachability queries pass a boolean BitSet from domain to domain, analytical queries often need to **repeat walks until convergence** or **carry and aggregate computed state** (costs, distances, capacities, or path witnesses) across hops.

---

## 1. Fixed-Point & Bounded Loops (`repeatUntilStable` & `repeat`)

For recursive hierarchies, supply chains, power-grid islanding, or Relationship-Based Access Control (ReBAC), Impulse Graph executes multi-hop loops directly in off-heap bitset registers with zero per-iteration heap allocations:

### 1.1 Unbounded Transitive Closure (`repeatUntilStable`)
Repeatedly steps across the specified relation until no new nodes are discovered ($\text{Frontier}_{t+1} == \text{Frontier}_t$), with optional inline CEL edge/node filtering:

```java
var groups = snap.domain("Group");

// Compute full transitive closure of parent groups
List<String> allAncestorGroups = groups.fromKey("grp_engineering_west")
    .repeatUntilStable("PARENT_GROUP")
    .toKeyList();

// Transitive closure with an inline CEL predicate
List<String> activeAncestors = groups.fromKey("grp_engineering_west")
    .repeatUntilStable("PARENT_GROUP", "edge.active == true")
    .toKeyList();
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
snap.domain("City").fromKey("ATL")
    .outWithState("FLIGHT_LEG", "state.min_cost:MIN = src.airport_fee + edge.ticket_price")
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
snap.domain("Warehouse").from(activeWarehouses)
    .outWithState("TRUCK_ROUTE", """
        state.lowest_cost:MIN = src.handling_cost + edge.freight_fee,
        state.best_warehouse:ARGMIN(state.lowest_cost) = src.id
        """)
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
```

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
