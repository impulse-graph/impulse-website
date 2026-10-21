# Go SDK & CGo VM Reference (`impulse-go`)

This reference documents the **Impulse Graph Engine Go SDK** (`github.com/impulse-graph/impulse-graph/go`, located in `impulse-graph-core/impulse-go`).

The Go SDK links directly against the C-ABI static kernel (`libimpulse_graph_static.a`) via CGo (`CGO_ENABLED=1`), exposing zero-copy `.imps` snapshot loading, fluent traversals, the `ImpulseVM` bytecode builder, live `DeltaLayer` compaction, and dynamic SIMD kernels.

---

## 1. Prerequisites & Building

Build the static C++ kernel first, then build or test the Go package:

```bash
cd impulse-graph-core/impulse-cpp
cmake -B build && cmake --build build

cd ../impulse-go
go test -v ./...
```

---

## 2. Snapshot Lifecycle & Reachability (`snapshot.go`)

```go
package main

import (
	"fmt"
	"log"

	impulse "github.com/impulse-graph/impulse-graph/go"
)

func main() {
	snap, err := impulse.OpenSnapshot("social_graph.imps")
	if err != nil {
		log.Fatalf("open failed: %v", err)
	}
	defer snap.Close()

	fmt.Printf("Version: %d, Domains: %d, Relations: %d\n",
		snap.Version(), snap.DomainCount(), snap.RelationCount())

	// Direct point reachability check on relation 0
	connected := snap.IsReachable(0, 0, 1)
	fmt.Printf("Edge (0 -> 1) exists: %v\n", connected)
}
```

---

## 3. Fluent Traversal & Bytecode VM (`traversal.go`, `vm.go`)

### 3.1 Fluent Traversal Pipeline

```go
friends, err := snap.Traverse("User", 0).
	Out("FOLLOWS").
	Out("FOLLOWS").
	ToSlice()
```

### 3.2 `QueryBuilder` & `VmContext`

```go
qb := impulse.NewQueryBuilder()
query := qb.
	InputNode(0).
	WalkEdge(0, 0).
	WalkEdge(0, 0).
	CollectBitset().
	Compile()

res, err := query.Execute(snap, 42)
if err == nil && res.IsOk() {
	fmt.Printf("Result Register: R%d, Raw Value: %d\n", res.ResultRegister, res.RawValue)
}
```

---

## 4. Single-Pass Snapshot Writer & Delta Compaction (`writer.go`, `delta.go`)

### 4.1 `Writer`

```go
writer, err := impulse.NewWriter("output.imps", 0)
if err != nil {
	log.Fatal(err)
}
defer writer.Close()

writer.AddDomain(0, impulse.KeyTypeInt64, "User")
rowOffsets := []uint32{0, 2, 4, 5, 5}
colIndices := []uint32{1, 2, 2, 3, 3}

_ = writer.AddRelation(0, 0, 0, 4, 5, 0, rowOffsets, colIndices)
_ = writer.Finalize()
```

### 4.2 `DeltaLayer` Overlay & Compaction

```go
delta := impulse.NewDeltaLayer(0, 0, "FOLLOWS")
defer delta.Close()

_ = delta.AddEdge(3, 1)
_ = delta.TombstoneEdge(0, 2)

_ = snap.CompactToFile([]*impulse.DeltaLayer{delta}, "compacted.imps")
```
