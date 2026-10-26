# Go, .NET (C#) & Node.js SDKs

In addition to Java 25, Python, C/C++20, and Rust, Impulse Graph provides official native bindings for **Go (CGo)**, **.NET 8+ (C# / F# P/Invoke)**, and **Node.js / Bun / TypeScript (N-API)**, all backed by the static C-ABI kernel (`libimpulse_graph_static.a`).

---

## 1. Go SDK (`impulse-go` via CGo)

Links directly against `libimpulse_graph_static.a` (`CGO_ENABLED=1`), exposing zero-copy `.imps` loading, CSR slice views (`GetRelationBuffers`), fluent `Traversal` pipelines, `ImpulseVM` bytecode execution (`QueryBuilder` + `ExecuteVM`), and single-pass `.imps` writing.

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

	// 1. Direct O(log d) reachability check & zero-copy CSR buffer slices
	connected := snap.IsReachable(0, 10, 42)
	offsets, targets, nodeCount, edgeCount, err := snap.GetRelationBuffers(0)
	if err != nil {
		log.Fatalf("buffer access failed: %v", err)
	}
	fmt.Printf("Edge (10 -> 42): %v (nodes=%d, edges=%d, offsets=%d, targets=%d)\n",
		connected, nodeCount, edgeCount, len(offsets), len(targets))

	// 2. Fluent VM QueryBuilder & ExecuteVM
	ctx, err := impulse.NewVMContext(snap)
	if err != nil {
		log.Fatalf("vm context failed: %v", err)
	}
	defer ctx.Close()

	state := impulse.NewVMState()
	state.SetQueryContext(ctx)

	bytecode := impulse.NewQueryBuilder().
		InputNode(0).
		WalkEdge(0, 1). // Relation 0: MEMBER_OF -> R1
		WalkEdge(1, 2). // Relation 1: PARENT_GROUP -> R2
		CollectBitset(2).
		Compile()

	if err := impulse.ExecuteVM(bytecode, state, 10); err != nil {
		log.Fatalf("VM execution failed: %v", err)
	}
	fmt.Printf("Result bitset handle in R2: %d\n", state.GetRegister(2))
}
```

---

## 2. .NET 8+ / C# SDK (`ImpulseGraph` via P/Invoke)

Provides deterministic `IDisposable` off-heap management (`Snapshot`, `VmContext`, `QueryBuilder`, `Query`, `ExecutionResult`) across Linux (`x64`/`arm64`), macOS (`arm64`), and Windows (`x64`).

```bash
dotnet add package ImpulseGraph
dotnet add package ImpulseGraph.Native
```

```csharp
using System;
using ImpulseGraph;
using ImpulseGraph.Vm;

using var snap = new Snapshot("rbac.imps");

Console.WriteLine($"Domains: {snap.DomainCount}, Relations: {snap.RelationCount}");

// 1. Direct O(log d) reachability check & relation directory inspection
bool reachable = snap.IsReachable(0, 10UL, 42UL);
var relEntry = snap.GetRelationEntry(0);

// 2. Fluent VM QueryBuilder & Snapshot.ExecuteQuery
using var ctx = new VmContext(snap);

Query query = new QueryBuilder()
    .InputNode(0)
    .WalkEdge(relationId: 0, dstReg: 1) // Relation 0: MEMBER_OF -> R1
    .WalkEdge(relationId: 1, dstReg: 2) // Relation 1: PARENT_GROUP -> R2
    .CollectBitset(reg: 2)
    .Compile();

ExecutionResult result = snap.ExecuteQuery(query, ctx, inputParam: 42UL);
Console.WriteLine($"VM Status: {result.Status}, R2 Handle: {result.GetRegister(2)}");
```

---

## 3. Node.js, Bun & TypeScript SDK (`impulse-graph` via N-API)

Built on N-API (`node-addon-api`) with zero external npm dependencies and full TypeScript declarations (`index.d.ts`). Exposes `Snapshot` (with fluent `.traverse(startNode)`), `VmContext` (with `Float32Array` / `Float64Array` / `BigUint64Array` vector views), `VmState`, `QueryBuilder`, `CompiledQuery`, and `Writer`.

```bash
npm install impulse-graph
```

```typescript
import { Snapshot, VmContext, VmState, QueryBuilder } from 'impulse-graph';

const snap = new Snapshot('rbac.imps');
const ctx = new VmContext(snap);

try {
  // 1. Direct reachability check
  const reachable: boolean = snap.isReachable(0, 10, 0, 42);

  // 2. Fluent VM QueryBuilder with fixed-point transitive closure
  const state = new VmState();
  const query = new QueryBuilder()
    .inputNode(0)
    .walkEdge(0) // Relation 0: MEMBER_OF
    .repeatUntilStable((b) => {
      b.walkEdge(1); // Relation 1: PARENT_GROUP
    })
    .collectBitset()
    .compile();

  const res = query.executeWithContext(ctx, state, 42);
  console.log('Execution OK:', res.isOk(), 'Group 7 reachable:', res.testBitset(ctx, 7));
} finally {
  ctx.destroy();
  snap.close();
}
```

---

## 4. Cross-SDK Method Equivalence

| Operation | Go (`impulse-go`) | .NET 8+ (`ImpulseGraph`) | Node.js / TS (`impulse-graph`) |
| :--- | :--- | :--- | :--- |
| **Open `.imps`** | `impulse.OpenSnapshot(path)` | `new Snapshot(path)` | `new Snapshot(path)` |
| **Domain / Relation Count** | `snap.DomainCount()` / `RelationCount()` | `snap.DomainCount` / `RelationCount` | — |
| **Direct CSR Check** | `snap.IsReachable(rel, src, tgt)` | `snap.IsReachable(rel, src, tgt)` | `snap.isReachable(srcDom, src, tgtDom, tgt)` |
| **Zero-Copy CSR Buffers** | `snap.GetRelationBuffers(rel)` | `snap.GetRelationEntry(rel)` | `snap.traverse(startNode)` |
| **VM Context** | `impulse.NewVMContext(snap)` | `new VmContext(snap)` | `new VmContext(snap)` |
| **Seed Input Node** | `qb.InputNode(dstReg)` | `qb.InputNode(dstReg)` | `qb.inputNode(dstReg)` |
| **Forward Walk (CSR)** | `qb.WalkEdge(relId, dstReg)` | `qb.WalkEdge(relId, dstReg)` | `qb.walkEdge(relId, flags)` |
| **Reverse Walk (CSC)** | `qb.CscWalk(relId, dstReg)` | `qb.CscWalk(relId, dstReg)` | `qb.walkCsc(relId)` |
| **Fixed-Point Loop** | — | — | `qb.repeatUntilStable(b => ...)` |
| **Execute VM Query** | `impulse.ExecuteVM(code, state, seed)` | `snap.ExecuteQuery(query, ctx, seed)` | `query.executeWithContext(ctx, state, seed)` |
| **Close / Unmap** | `snap.Close()` | `snap.Dispose()` (`using`) | `snap.close()` |
