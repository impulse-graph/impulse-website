# Typed Graph Model

The Impulse Graph Engine enforces a strict, strongly-typed domain model designed to collapse runtime overhead and compress memory footprints.

## EntityTypes and Relations

The graph topology is bounded by the schema.
- **EntityTypes**: Nodes are grouped into discrete `EntityTypes`. You must declare an `EntityType` and an estimated capacity upfront. 
- **Relations**: Edges are strictly directed connections denoted as a `Relation` between a source `EntityType` and a target `EntityType`. Labeled edge filters can apply to these relations to support high-fanout filtering without loading properties.

## DenseIDs

Within the core C-ABI engine, nodes do not have string names or UUIDs. Instead, every node is assigned a **DenseID** (a 64-bit `uint64_t`). A DenseID acts effectively as a direct array index ($O(1)$ lookup time) into the CSR offsets block. This dense packing is what enables sub-microsecond traversals.

## BusinessKeys & IdMapper

In real-world applications, your data has external primary keys (UUIDs, usernames, account numbers). Impulse Graph handles this using the `IdMapper` subsystem. The `IdMapper` resolves external **BusinessKeys** into internal **DenseIDs** at the edges of the application boundary. 

Once resolved to a `DenseID`, the graph traversal core processes the query entirely via integers, pushing throughput into the millions of queries per second.
