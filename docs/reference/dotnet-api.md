# .NET / C# SDK Reference (`impulse-dotnet`)

This reference documents the **Impulse Graph Engine .NET 8+ SDK** (`ImpulseGraph`, located in `impulse-graph-core/impulse-dotnet`).

The .NET SDK binds to the C-ABI native library (`libimpulse_graph.dylib` / `.so` / `.dll`) via P/Invoke, providing deterministic `IDisposable` off-heap resource management for `Snapshot`, `Writer`, `VmContext`, `QueryBuilder`, and `CompiledQuery`.

---

## 1. Installation & NuGet Packages

```bash
dotnet add package ImpulseGraph
dotnet add package ImpulseGraph.Native
```

| Package | Description |
| :--- | :--- |
| **`ImpulseGraph`** | Managed C# API (`Snapshot`, `Writer`, `ImpulseGraph.Vm.QueryBuilder`, `VmContext`). |
| **`ImpulseGraph.Native`** | Cross-platform native C-ABI binaries for Linux (`x64`/`arm64`), macOS (`arm64`), and Windows (`x64`). |
| **`ImpulseGraph.FSharp`** | Idiomatic F# pipeline operators and computation expressions. |

---

## 2. Snapshot & Reachability API (`ImpulseGraph.Snapshot`)

```csharp
using System;
using ImpulseGraph;

using var snap = new Snapshot("rbac_snapshot.imps");

Console.WriteLine($"Magic: 0x{snap.Magic:X8}, Version: {snap.Version}");
Console.WriteLine($"Domains: {snap.DomainCount}, Relations: {snap.RelationCount}");

// Direct O(log d) CSR edge check on relation 0
bool reachable = snap.IsReachable(relationIndex: 0, srcId: 10UL, tgtId: 42UL);
```

---

## 3. Fluent Bytecode VM API (`ImpulseGraph.Vm`)

Constructs and executes 64-bit `impOps` bytecode pipelines on the native `ImpulseVM`:

```csharp
using System;
using ImpulseGraph;
using ImpulseGraph.Vm;

using var snap = new Snapshot("social_graph.imps");

// Build 2-hop traversal with fixed-point loop
CompiledQuery query = new QueryBuilder()
    .InputNode(0)
    .WalkEdge(0)
    .RepeatUntilStable(q => q.WalkEdge(1))
    .CollectBitset()
    .Compile();

using var ctx = new VmContext(snap);
using var state = new VmState();

QueryResult result = query.ExecuteWithContext(ctx, state, inputParam: 100UL);
if (result.IsOk)
{
    bool isMember = result.TestBitset(ctx, nodeId: 42UL);
    Console.WriteLine($"Node 42 reachable: {isMember}");
}
```

### Core Classes (`ImpulseGraph.Vm`)

* **`QueryBuilder`**: Fluent builder emitting 8-byte `impulse_instruction_t` instructions (`InputNode`, `InputSet`, `WalkEdge`, `WalkEdgeFiltered`, `WalkCsc`, `FilterNode`, `UnionWith`, `IntersectWith`, `DifferenceWith`, `Cardinality`, `MatrixVectorMul`, `Afforest`, `SampleNeighbors`, `RebacCheck`, `Repeat`, `RepeatUntilStable`, `CollectBitset`, `CollectArray`, `Compile`).
* **`CompiledQuery`**: Immutable compiled bytecode buffer (`Execute`, `ExecuteWithContext`, `InstructionCount`, `ResultRegister`).
* **`QueryResult`**: Value wrapper (`Status`, `ResultRegister`, `ResultType`, `RawValue`, `IsOk`, `AsInt()`, `AsFloat()`, `AsDouble()`, `TestBitset(ctx, nodeId)`).
* **`VmContext`**: Off-heap handle pool for bitsets, float/double vectors, node vectors, string vectors, and value maps.
