# Core Concepts

Understanding the Impulse Graph Engine requires familiarity with a few foundational abstractions. Because the engine is polyglot, these exact concepts carry over directly whether you're writing Java, C++, or Rust.

### Glossary

* **Snapshot**: The `ImpulseGraphSnapshot` is an immutable, memory-mapped binary file (`.imps`) optimized for zero-copy reads. It represents the state of the graph at a specific point in time and serves as the baseline data structure.
* **EntityType**: A distinct class or type of node (e.g., `User`, `Transaction`, `Substation`). Every node in the graph belongs to an `EntityType`.
* **Relation**: A directed, typed edge connecting a source node to a target node (e.g., `User -[FOLLOWS]-> User`). Relations are strictly structured and pre-declared.
* **CsrDeltaLayer**: A dynamic, in-memory overlay structure that handles live graph mutations (insertions, deletions, updates) overlaid on top of a read-only immutable snapshot.
* **GraphView**: A unified, thread-safe projection of the graph. A view can encapsulate a pure `ImpulseGraphSnapshot`, or an `ImpulseGraph` combining a base snapshot with a `CsrDeltaLayer`. All queries run against a `GraphView`.
* **QueryContext**: A localized runtime context tied to a thread, providing the resources and memory buffers necessary to execute a query over a `GraphView`.
* **DenseID**: A zero-indexed, 64-bit integer representing the physical address of a node. All core graph traversals operate purely on DenseIDs for maximum performance.

Next, explore how [Snapshots](../concepts/snapshots.md) operate under the hood to achieve sub-millisecond load times.
