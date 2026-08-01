# Building Queries

The Query Builder API is designed to create immutable, serializable query plans safely and ergonomically.

## The Builder Pattern

In Java, Rust, and Python, queries are built using a fluent builder interface. The builder is decoupled from any graph instance — you build the plan once and execute it later.

```java
// === STARTUP: build once ===
ImpulseQuery<RoaringBitmap> userRolesQuery = ImpulseQuery.builder()
    .input(EntityType.USER, ArgType.ROARING_BITSET)
    .walkEdge("userToGroup")
    .walkEdge("groupToRole")
    .collect(ReturnType.ROARING_BITSET);
```

## Immutability and Reusability

An `ImpulseQuery` instance is deeply immutable. It holds no reference to any snapshot, `ImpulseGraph`, or schema instance. It is a pure tree of operation nodes that you can safely share across all threads in your application.

## Type Safety Guarantees

The builder enforces type safety. There are two tiers of type safety available:

1. **Stringly-typed**: `walkEdge("userToGroup")` — validated against the schema either at `build()` or lazily at first `compile()`.
2. **Code-generated**: `walkEdge(Relation.USER_TO_GROUP)` — using typed constants from `impulse-codegen` for full compile-time safety and IDE autocomplete.

The builder is also parameterized on the current pipeline entity type, meaning it tracks the graph schema as you build. If you attempt to feed the output of one step into an incompatible step, the compiler (or builder validation) catches it.
