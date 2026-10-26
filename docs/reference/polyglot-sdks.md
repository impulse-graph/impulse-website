# Go, .NET (C#) & Node.js SDKs

In addition to Java 25, Python, C/C++20, and Rust, Impulse Graph provides official native bindings for **Go (CGo)**, **.NET 8+ (C# / F# P/Invoke)**, and **Node.js / Bun / TypeScript (N-API)**, all backed by the static C-ABI kernel (`libimpulse_graph_static.a`).

---

## 1. Go SDK (`impulse-go` via CGo)

Links directly against `libimpulse_graph_static.a` (`CGO_ENABLED=1`), exposing zero-copy `.imps` loading, CSR slice views, `ImpulseVM` bytecode execution (`QueryBuilder`), and single-pass `.imps` writing.

```go
package main

import (
	"fmt"
	"log"

	impulse "github.com/impulse-graph/impulse-graph/go"
)

func main() {
	snap, err := impulse.OpenSnapshot("rbac.imps")
	if err != nil {
		log.Fatalf("open failed: %v", err)
	}
	defer snap.Close()

	// 1. Direct O(log d) reachability check
	connected := snap.IsReachable(0, 10, 42)
	fmt.Printf("Edge (10 -> 42) exists: %v\n", connected)

	// 2. Fluent VM QueryBuilder with fixed-point transitive closure
	ctx := impulse.NewVmContext(snap)
	defer ctx.Close()

	var state impulse.VmState
	state.SetQueryContext(ctx)

	query := impulse.NewQueryBuilder().
		InitInputNode(0).
		WalkEdge(0, 1, 0).          // Relation 0: MEMBER_OF
		RepeatUntilStable(1, 2, 1). // Relation 1: PARENT_GROUP
		CollectBitset(3, 2).
		Compile()

	status := query.Execute(&state, 10)
	fmt.Printf("VM execution status: %v\n", status)
}
```

---

## 2. .NET 8+ / C# SDK (`ImpulseGraph` via P/Invoke)

Provides deterministic `IDisposable` off-heap management (`Snapshot`, `VmContext`, `QueryBuilder`, `Writer`) and zero-copy `ReadOnlySpan<uint>` views across Linux (`x64`/`arm64`), macOS (`arm64`), and Windows (`x64`).

```bash
dotnet add package ImpulseGraph
dotnet add package ImpulseGraph.Native
```

```csharp
using System;
using ImpulseGraph;

using var snap = new Snapshot("rbac.imps");

Console.WriteLine($"Domains: {snap.DomainCount}, Relations: {snap.RelationCount}");

// 1. Zero-copy ReadOnlySpan<uint> views over CSR arrays
ReadOnlySpan<uint> rowOffsets = snap.GetRowOffsetsSpan(0);
ReadOnlySpan<uint> colIndices = snap.GetColIndicesSpan(0);

// 2. Fluent VM QueryBuilder with transitive closure
using var ctx = new VmContext(snap);
var state = new VmState { QueryContext = ctx.DangerousGetHandle() };

var query = new QueryBuilder()
    .InitInputNode(0)
    .WalkEdge(0, 1, 0)          // Relation 0: MEMBER_OF
    .RepeatUntilStable(1, 2, 1) // Relation 1: PARENT_GROUP
    .CollectBitset(3, 2)
    .Compile();

VmStatus status = query.Execute(state, 42);
```

---

## 3. Node.js, Bun & TypeScript SDK (`impulse-graph` via N-API)

Built on N-API (`node-addon-api`) with zero external npm dependencies and full TypeScript declarations (`index.d.ts`). Exposes zero-copy `TypedArray` views (`Uint32Array`) directly over `mmap` snapshot regions as well as `VmContext`, `QueryBuilder`, and `Writer`.

```bash
npm install impulse-graph
```

```typescript
import { Snapshot, VmContext, VmState, QueryBuilder, ExecuteQuery } from 'impulse-graph';

const snap = new Snapshot('rbac.imps');

try {
  // 1. Zero-copy TypedArray views over 128-byte-aligned CSR buffers
  const rowOffsets: Uint32Array = snap.getRowOffsets(0);
  const colIndices: Uint32Array = snap.getColIndices(0);

  // 2. Fluent VM QueryBuilder with fixed-point transitive closure
  const ctx = new VmContext(snap);
  const state = new VmState();
  state.setQueryContext(ctx);

  const instructions = new QueryBuilder()
    .initInputNode(0)
    .walkEdge(0, 1, 0)          // Relation 0: MEMBER_OF
    .repeatUntilStable(1, 2, 1) // Relation 1: PARENT_GROUP
    .collectBitset(3, 2)
    .compile();

  const status = ExecuteQuery(instructions, state, 42);
  console.log('Execution status:', status);
} finally {
  snap.close();
}
```

---

## 4. Cross-SDK Method Equivalence

| Operation | Go (`impulse-go`) | .NET 8+ (`ImpulseGraph`) | Node.js / TS (`impulse-graph`) |
| :--- | :--- | :--- | :--- |
| **Open `.imps`** | `impulse.OpenSnapshot(path)` | `new Snapshot(path)` | `new Snapshot(path)` |
| **Domain / Relation Count** | `snap.DomainCount()` / `RelationCount()` | `snap.DomainCount` / `RelationCount` | `snap.domainCount()` / `relationCount()` |
| **Direct CSR Check** | `snap.IsReachable(rel, src, tgt)` | `snap.IsReachable(rel, src, tgt)` | `snap.isReachable(rel, src, tgt)` |
| **Zero-Copy CSR Slices** | `snap.GetRowOffsets(rel)` | `snap.GetRowOffsetsSpan(rel)` | `snap.getRowOffsets(rel)` |
| **VM Context** | `impulse.NewVmContext(snap)` | `new VmContext(snap)` | `new VmContext(snap)` |
| **Forward Walk (CSR)** | `qb.WalkEdge(src, dst, rel)` | `qb.WalkEdge(src, dst, rel)` | `qb.walkEdge(src, dst, rel)` |
| **Reverse Walk (CSC)** | `qb.WalkCsc(src, dst, rel)` | `qb.WalkCsc(src, dst, rel)` | `qb.walkCsc(src, dst, rel)` |
| **Fixed-Point Loop** | `qb.RepeatUntilStable(s, d, r)` | `qb.RepeatUntilStable(s, d, r)` | `qb.repeatUntilStable(s, d, r)` |
| **Close / Unmap** | `snap.Close()` | `snap.Dispose()` (`using`) | `snap.close()` |
