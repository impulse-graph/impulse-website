# Schema Evolution Rules

The Impulse Graph engine separates the **Query schema requirement** (defined in code) from the **Snapshot actual schema** (encoded in the `.imps` file Section 2). 

This design ensures that queries are durable across snapshot generations. However, when you change the snapshot generator to emit a new schema, you must follow specific evolution rules to avoid breaking existing queries.

## The Rule: Name is Identity

In Impulse Graph, the **String Name** (e.g., `"userToGroup"`) is the semantic contract. The underlying integer ID (e.g., `0x10`) is a per-snapshot implementation detail that the compiler resolves at execution time.

## Safe vs. Breaking Changes

| Change in Snapshot Generation | Impact on Queries | Safe? |
|-------------------------------|------------------|-------|
| Add new relation | Zero impact — queries ignore unknown relations | ✅ Always safe |
| Add new entity type | Zero impact | ✅ Always safe |
| Add new nodes to existing type | Zero impact — `universe(T)` returns more nodes | ✅ Safe (Result sets may change) |
| Change a relation's integer ID | Transparent — name lookup re-resolves the ID on `GraphView` load | ✅ Safe |
| Rename a relation | All queries referencing old name break at compile time | ❌ Breaking |
| Change relation source/target type | Structural type mismatch → query rejected at compile time | ❌ Breaking |
| Remove a relation | Queries referencing it fail at compile time | ❌ Breaking |

## ID Remapping Process

When `GraphView.of(snapshot)` is called, the engine reads Section 2 of the `.imps` file.

1. It hashes the relationships the query actually uses.
2. It looks up the relation names to find their *current* integer IDs in this specific snapshot.
3. If the IDs have changed from a previous compilation, a lightweight recompilation occurs to update the opcode stream with the new integer indices. 

Because of this, tools like `impulse-opt` are free to re-number relations for memory alignment or RCM ordering without breaking downstream applications.
