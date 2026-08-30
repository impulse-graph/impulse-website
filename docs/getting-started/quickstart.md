# Quickstart

This guide will walk you through the end-to-end lifecycle of working with Impulse Graph Engine: loading a binary snapshot, defining a schema, and executing a traversal.

Since Impulse Graph is polyglot, the APIs are idiomatic to your language but map exactly to the same underlying C-ABI execution engine.

### 1. Define the Schema and Load the Snapshot

Impulse Graph uses memory-mapped files (`mmap`) to load snapshots in sub-milliseconds, regardless of size. First, you define the entity and relation schema, and then you map the `.imps` snapshot file.

=== "Java"
    ```java
    import org.impulsegraph.api.ImpulseGraphSnapshot;
    import org.impulsegraph.storage.csr.BinarySnapshotLoader;
    import java.lang.foreign.Arena;
    import java.nio.file.Path;

    public class Quickstart {
        public static void main(String[] args) throws Exception {
            // 1. Manage off-heap lifecycle with a shared Arena
            try (Arena arena = Arena.ofShared()) {
                // 2. Map snapshot direct from disk (< 1 ms cold start)
                var loaded = BinarySnapshotLoader.loadSnapshot(Path.of("graph_v1.imps"), arena);
                ImpulseGraphSnapshot snap = loaded.getGraph();

                // 3. Execute domain-anchored traversals
                var friends = snap.domain("User").from(42).out("FOLLOWS").toList();
                System.out.println("User 42 follows: " + friends);
            }
        }
    }
    ```

=== "C++"
    ```cpp
    #include <impulse_graph.h>
    #include <iostream>

    int main() {
        // 1. Define the Graph Schema
        auto schema = impulse::GraphSchema::Builder()
            .addEntityType("User", 1000000)
            .addRelation("User", "FOLLOWS", "User")
            .build();

        // 2. Map the snapshot directly from disk (Zero-Copy)
        auto snapshot = impulse::ImpulseGraphSnapshot::load("graph_v1.imps", schema);
        
        // 3. Create a read-only GraphView
        auto view = snapshot->createView();
        
        // ... (proceed to query)
        return 0;
    }
    ```

=== "Rust"
    ```rust
    use impulse_graph::core::{GraphSchema, ImpulseGraphSnapshot, GraphView};

    fn main() -> Result<(), Box<dyn std::error::Error>> {
        // 1. Define the Graph Schema
        let schema = GraphSchema::builder()
            .add_entity_type("User", 1_000_000)
            .add_relation("User", "FOLLOWS", "User")
            .build()?;

        // 2. Map the snapshot directly from disk (Zero-Copy)
        let snapshot = ImpulseGraphSnapshot::load("graph_v1.imps", &schema)?;
        
        // 3. Create a read-only GraphView
        let view = snapshot.create_view();
        
        // ... (proceed to query)
        Ok(())
    }
    ```

### 2. Execute a Graph Query

Queries are executed against a `GraphView` within a `QueryContext`. The engine guarantees thread-safe, lock-free reads over the topology.

=== "Java"
    ```java
    // Multi-seed batch frontier with CEL attribute filtering
    List<Long> targets = snap.domain("User")
        .from(10, 20, 30)
        .filter("node.age >= 21")
        .out("FOLLOWS")
        .toList();

    System.out.println("Surviving target users: " + targets);
    ```

=== "C++"
    ```cpp
    // ... setup code from above

    // Build the query context
    auto ctx = view->createQueryContext();
    uint64_t userId = 42;
    
    // Zero-copy SIMD traversal
    auto targets = ctx->traverse(userId, "FOLLOWS");
    
    std::cout << "User " << userId << " follows:" << std::endl;
    while (targets.hasNext()) {
        std::cout << "- Node ID: " << targets.next() << std::endl;
    }
    ```

=== "Rust"
    ```rust
    // ... setup code from above

    // Build the query context
    let mut ctx = view.create_query_context();
    let user_id: u64 = 42;
    
    // Zero-copy SIMD traversal
    let mut targets = ctx.traverse(user_id, "FOLLOWS")?;
    
    println!("User {} follows:", user_id);
    while let Some(target_id) = targets.next() {
        println!("- Node ID: {}", target_id);
    }
    ```
