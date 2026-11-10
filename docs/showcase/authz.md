# Showcase: ReBAC Authorization (Zanzibar)

The **`impulse-authz`** showcase models enterprise hierarchical permissions (users, groups, roles, datasets) and demonstrates how Impulse Graph powers sub-microsecond, fine-grained **Relationship-Based Access Control (ReBAC)**—modeled after Google's Zanzibar architecture—directly inside your application process.

---

## 1. The Real-World Problem

In modern enterprise software, permissions aren't just simple role strings—they form a deep hierarchy of relationships:

* A `User` belongs to a `Group` (which may be nested inside parent `Group`s).
* A `Group` is assigned a `Role`.
* A `Role` grants `Permission` over a `Folder` or `Resource` (which itself has child `Document`s).

Answering *"Can User $U$ edit Document $D$?"*—or worse, *"Which of these 10,000 search results is User $U$ allowed to see?"*—requires walking a multi-hop graph on **every single API request**. Traditional SQL recursive CTEs or external authorization microservices add milliseconds of network and join latency to every call.

---

## 2. How Impulse Graph Solves It

Because authorization policies are read-heavy and change at a human/administrative cadence, they fit Impulse Graph's **"mmap and go"** model naturally:

1. **Multi-Domain Set Traversal**: Starting from a `User`, the query steps across `MEMBER_OF` (with transitive group nesting via `repeatUntilStable`), `HAS_ROLE`, and `GRANTS_ACCESS_TO` to reach the `Resource` domain.
2. **Set Semantics Eliminate Redundant Paths**: If a user belongs to 5 overlapping groups that all grant access to the same parent folder, Impulse collapses those converging paths into a single bit at each step—never walking the folder's children multiple times.
3. **Zero-Allocation Early Exit & Point Tests**: When an intermediate frontier empties (e.g. a user belongs to no groups granting access), the VM halts immediately (`FLAG_HALT_ON_EMPTY`). Single-resource access is verified via an $O(1)$ bit test over the resulting off-heap BitSet (`toBitSet().get((int) targetDenseId)`) without heap allocations.

!!! note "Benchmark Context"
    Sub-microsecond query latencies (`0.026 µs – 0.552 µs`) were measured in empirical microbenchmarks (`JsonVsCsrBenchmarkRunner`) evaluating multi-hop CSR traversals over a simulated directory corpus of 600,000 users with realistic group/role hierarchies (compared directly against Jackson JSON serialization cost).

=== "Java 25 (Fluent API)"
    ```java
    // 1. Check if 'usr_alice' has transitive access to 'doc_quarterly_report'
    long targetDocId = snap.domain("Resource").toDenseId("doc_quarterly_report");
    boolean isAllowed = snap.domain("User")
        .fromKey("usr_alice")
        // Walk direct and nested group memberships until fixed-point
        .out("MEMBER_OF")
        .repeatUntilStable("PARENT_GROUP")
        .out("HAS_ROLE")
        .out("GRANTS_ACCESS_TO")
        .toBitSet()
        .get((int) targetDocId);

    // 2. Or retrieve the full BitSet of all accessible resources in one pass
    //    to filter a search result list in-process in nanoseconds:
    ImpulseBitSet accessibleResources = snap.domain("User")
        .fromKey("usr_alice")
        .out("MEMBER_OF")
        .repeatUntilStable("PARENT_GROUP")
        .out("HAS_ROLE")
        .out("GRANTS_ACCESS_TO")
        .toBitSet();
    ```

=== "ImpLog (Declarative Datalog)"
    ```prolog
    // Transitive group membership and resource authorization in ImpLog (.implog)
    in_group(U, G) :- member_of(U, G).
    in_group(U, ParentG) :- in_group(U, ChildG), group_parent(ChildG, ParentG).

    can_access(U, R) :- in_group(U, G), has_role(G, Role), grants_access(Role, R).
    ```

---

## 3. Keeping Permissions Fresh: Periodic Rebuild & Atomic Swap

How do permission changes propagate without introducing reader locks?

1. Administrative permission updates write to your system-of-record database (e.g., PostgreSQL).
2. A background worker periodically compiles a fresh `.imps` authorization snapshot in seconds from your primary database (e.g. via JDBC or CDC Kafka stream) and publishes it to blob storage or local NVMe.
3. Application pods `mmap` the new `.imps` file in `< 1 ms` and perform a **zero-downtime Blue/Green atomic pointer swap** (see [Changing Data & Live Updates](../getting-started/handling-mutations.md)). Active API requests continue running with **zero locks** and **zero GC pauses**.
