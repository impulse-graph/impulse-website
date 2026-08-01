# Schema Definition

Before loading data or executing queries, Impulse Graph requires an explicit schema. This bounded approach ensures the engine knows exactly how to allocate memory segments and compress node identities.

## Defining the Topology

The `GraphSchema` defines the shape of the graph:

1. **EntityTypes**: Named nodes. A graph must define at least one `EntityType`.
2. **Declared Capacity**: When defining an `EntityType`, you must declare its estimated maximum capacity (node count). This allows the snapshot builder to pre-allocate exact contiguous memory blocks for optimal $O(1)$ indexing.
3. **Relations**: Directed edges are defined as connecting a source `EntityType` to a target `EntityType` with a specific verb/label.

### Example Schema

```java
GraphSchema schema = GraphSchema.builder()
    // Define an EntityType named "User" capable of holding up to 10M nodes
    .addEntityType("User", 10_000_000)
    
    // Define an EntityType named "Product" holding up to 5M nodes
    .addEntityType("Product", 5_000_000)
    
    // Define relationships between them
    .addRelation("User", "PURCHASED", "Product")
    .addRelation("User", "FOLLOWS", "User")
    
    .build();
```

## Name as Identity vs Integer IDs

In the schema, string names (`"User"`, `"PURCHASED"`) provide human-readable semantic identity. However, under the hood, the engine maps these exact names to compact 16-bit integers during the Snapshot Header mapping phase. 

This hybrid approach allows developers to write expressive domain code while the core kernel executes entirely on integers, achieving millions of operations per second per core.
