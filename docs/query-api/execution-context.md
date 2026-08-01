# Execution Context

To achieve high-throughput, lock-free query evaluation, the API enforces explicit memory ownership through `QueryContext`.

## `QueryContext`

The `QueryContext` holds all mutable intermediate state (scratch buffers) for a single execution. It is sized exactly at compile time and is **explicitly owned** by the caller.

```java
// Pre-allocated context per worker slot
QueryContext ctx = userRolesQuery.createContext();

// Hot path: allocation-free execution
RoaringBitmap result = userRolesQuery.execute(ctx, view, inputBitset);
```

## Why Not ThreadLocal?

`ThreadLocal` is historically common in Java, but fails in the Project Loom / virtual threads era:

* **Virtual threads (100K+ vthreads)**: Allocating scratch buffers per thread results in Out-Of-Memory (OOM).
* **Coroutines**: `ThreadLocal` can accidentally leak state across logically separate coroutines sharing a carrier thread.

`QueryContext` solves this through explicit parameter passing.

## `QueryContextPool`

For pooled environments (like an HTTP server serving requests), use a `QueryContextPool` to bound memory usage:

```java
QueryContextPool<Boolean> pool = QueryContextPool.of(canReadQuery, 256);

// Per request (zero allocation):
try (QueryContext ctx = pool.acquire()) {
    boolean allowed = canReadQuery.execute(ctx, view, userId);
} // ctx is returned to pool automatically
```
