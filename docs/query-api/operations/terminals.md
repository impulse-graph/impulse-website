# Terminal Collectors

Terminals finalize the query pipeline and dictate the return type of the `.execute()` method.

## Materializing Terminals

* **`collect(ROARING_BITSET)`**: Returns a `RoaringBitmap`. Ideal for sparse, compressed sets.
* **`collect(DENSE_BITSET)`**: Returns dense bitset words (e.g., `long[]`). Excellent for downstream SIMD processing.
* **`collect(NODE_ARRAY)`**: Returns a sorted array of node IDs. Good for API serialization.

## Scalar Terminals

* **`collect(COUNT)`**: Returns only the cardinality (`long`), avoiding full materialization.
* **`collect(EXISTS)`**: Returns `boolean` `true` if the result is non-empty. Heavily used in hot-path authorization checks.
* **`collect(SINGLE_NODE)`**: Returns an `OptionalLong` or equivalent, used in conjunction with `walkTarget`.

## Direct Operations

* **`contains(nodeId)`**: Returns a `boolean` if the resulting set contains the specified node ID, avoiding materialization.

## Zero-Allocation Execution (`executeInto`)

For ultimate performance, the engine allows you to supply your own output buffer via `executeInto()`:

```java
// Zero allocation: caller owns the output buffer and reuses it
int resultWords = query.executeInto(ctx, view, inputBitset, outputWordArray);
```
