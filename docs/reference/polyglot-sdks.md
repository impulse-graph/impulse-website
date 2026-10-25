# Go, .NET (C#) & Node.js SDKs

In addition to Java 25, Python, C/C++20, and Rust, Impulse Graph provides official native bindings for **Go (CGo)**, **.NET 8+ (C# / F# P/Invoke)**, and **Node.js / Bun / TypeScript (N-API)**, all backed by the static C-ABI kernel (`libimpulse_graph_static.a`).

---

## 1. Go SDK (`impulse-go` via CGo)

Links directly against `libimpulse_graph_static.a` (`CGO_ENABLED=1`), exposing zero-copy `.imps` loading, domain-bound traversals, prepared statements, and single-pass `.imps` writing.

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

	// 2. Domain-anchored fluent traversal with transitive closure
	groups, err := snap.Domain("User").
		FromKey("usr_alice").
		Out("MEMBER_OF").
		RepeatUntilStable("PARENT_GROUP").
		ToKeys()
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Reachable groups: %v\n", groups)
}
```

---

## 2. .NET 8+ / C# SDK (`ImpulseGraph` via P/Invoke)

Provides deterministic `IDisposable` off-heap management for `Snapshot`, `Statement`, and `Writer` across Linux (`x64`/`arm64`), macOS (`arm64`), and Windows (`x64`).

```bash
dotnet add package ImpulseGraph
dotnet add package ImpulseGraph.Native
```

```csharp
using System;
using ImpulseGraph;

using var snap = new Snapshot("rbac.imps");

Console.WriteLine($"Domains: {snap.DomainCount}, Relations: {snap.RelationCount}");

// 1. Domain-anchored fluent traversal (zero lambdas)
string[] groups = snap.Domain("User")
    .FromKey("usr_alice")
    .Out("MEMBER_OF")
    .RepeatUntilStable("PARENT_GROUP")
    .ToKeyArray();

// 2. Parameterized prepared statement
using var stmt = snap.Prepare(
    "MATCH (u:User)-[:PURCHASED]->(p:Product) " +
    "WHERE u._key = $userKey AND p.price <= $maxPrice " +
    "RETURN p._id, p.price"
);
stmt.BindString("userKey", "usr_alice");
stmt.BindDouble("maxPrice", 99.95);

using var result = stmt.Execute();
ReadOnlySpan<ulong> productIds = result.GetColumnSpan<ulong>(0);
ReadOnlySpan<double> prices    = result.GetColumnSpan<double>(1);
```

---

## 3. Node.js, Bun & TypeScript SDK (`impulse-graph` via N-API)

Built on N-API (`node-addon-api`) with zero external npm dependencies and full TypeScript declarations (`index.d.ts`). Exposes zero-copy `TypedArray` views (`Uint32Array`, `Float32Array`, `BigUint64Array`) directly over `mmap` snapshot regions.

```bash
npm install impulse-graph
```

```typescript
import { Snapshot, Writer } from 'impulse-graph';

const snap = new Snapshot('rbac.imps');

try {
  // 1. Domain-anchored fluent traversal with CEL predicate and transitive closure
  const accessibleDocs: string[] = snap
    .domain('User')
    .fromKey('usr_alice')
    .out('MEMBER_OF')
    .repeatUntilStable('PARENT_GROUP')
    .out('HAS_PERMISSION', 'edge.scope == $scope')
    .withParam('scope', 'doc:write')
    .toKeys();

  console.log('Accessible documents:', accessibleDocs);

  // 2. Zero-copy TypedArray view of a 128-byte-aligned SoA attribute column
  const prices: Float32Array = snap.getAttributeFloat32Array('Product', 'price');
  console.log('First product price:', prices[0]);
} finally {
  snap.close();
}
```

---

## 4. Cross-SDK Method Equivalence

| Operation | Go (`impulse-go`) | .NET 8+ (`ImpulseGraph`) | Node.js / TS (`impulse-graph`) |
| :--- | :--- | :--- | :--- |
| **Open `.imps`** | `impulse.OpenSnapshot(path)` | `new Snapshot(path)` | `new Snapshot(path)` |
| **Bind Domain** | `snap.Domain("User")` | `snap.Domain("User")` | `snap.domain('User')` |
| **Seed Frontier** | `.From(ids...)` / `.FromKey(k)` | `.From(ids)` / `.FromKey(k)` | `.from(ids)` / `.fromKey(k)` |
| **Step Relation** | `.Out(rel)` / `.In(rel)` | `.Out(rel)` / `.In(rel)` | `.out(rel)` / `.in(rel)` |
| **CEL Filter** | `.Filter(cel)` | `.Filter(cel)` | `.filter(cel)` |
| **Fixed-Point Loop** | `.RepeatUntilStable(rel)` | `.RepeatUntilStable(rel)` | `.repeatUntilStable(rel)` |
| **Prepared Query** | `snap.Prepare(query)` | `snap.Prepare(query)` | `snap.prepare(query)` |
| **Close / Unmap** | `snap.Close()` | `snap.Dispose()` (`using`) | `snap.close()` |
