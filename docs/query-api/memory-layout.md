# Deterministic Memory Layout

Everything the engine needs to know about memory at execute time is derivable at compile time. This allows you to inspect and pre-allocate memory buffers securely.

## `QueryMemoryLayout`

`QueryMemoryLayout` is an object produced during compilation that describes the exact byte footprint of a query plan's intermediate steps.

```java
QueryMemoryLayout layout = query.layout(schema);

System.out.printf("Total memory per concurrent query slot: %,d bytes", layout.totalBytes());
```

It sizes scratch buffers according to the **capacity** defined in the schema for each entity type involved in the query.

## Caller-Provided Memory

You can achieve a completely allocation-free pipeline by giving the engine memory that you allocated up-front (heap array, off-heap via Panama, or a Direct ByteBuffer).

```java
ByteBuffer mem = ByteBuffer.allocateDirect((int) layout.totalBytes());
QueryContext ctx = query.createContext(mem, layout);
```

## Scratch Strategies

For extremely large entity types (1B+ nodes), a dense scratch `long[]` buffer becomes prohibitively large (e.g., 125MB per intermediate buffer).

The schema allows defining a `ScratchStrategy`:

* **`DENSE`**: Fastest, SIMD-friendly, pre-allocated `long[]`.
* **`ROARING`**: Pre-allocated container pools. Uses much less memory but is slower.
* **`ADAPTIVE`**: Chooses automatically based on observed density.
