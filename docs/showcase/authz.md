# Showcase: ReBAC Authorization (Zanzibar)

The **`impulse-authz`** showcase demonstrates how Impulse Graph powers sub-microsecond, fine-grained **Relationship-Based Access Control (ReBAC)**—modeled after Google's Zanzibar architecture—directly inside your application process.

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
3. **Sub-Microsecond Early Exit**: When checking access to a single resource, the VM checks whether the target `Resource` Dense ID bit is set and short-circuits immediately (`FLAG_HALT_ON_EMPTY`).

=== "Java 25 (Fluent API)"
    ```java
    // 1. Check if 'usr_alice' has transitive access to 'doc_quarterly_report'
    boolean isAllowed = snap.domain("User")
        .fromKey("usr_alice")
        // Walk direct and nested group memberships until fixed-point
        .out("MEMBER_OF")
        .repeatUntilStable("PARENT_GROUP")
        .out("HAS_ROLE")
        .out("GRANTS_ACCESS_TO")
        .toKeyList()
        .contains("doc_quarterly_report");

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
2. A background worker compiles a fresh `.imps` authorization snapshot in seconds (or consumes Debezium CDC events) and publishes it to blob storage / local NVMe.
3. Application pods `mmap` the new `.imps` file in `< 1 ms` and perform a **zero-downtime Blue/Green atomic pointer swap** (see [Changing Data & Live Updates](../getting-started/handling-mutations.md)). Active API requests continue running with **zero locks** and **zero GC pauses**.
