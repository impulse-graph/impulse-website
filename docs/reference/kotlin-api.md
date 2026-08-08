# Kotlin API Reference (`impulse-kotlin`)

Welcome to the **Kotlin Extensions & Idiomatic DSL API Reference** for the Impulse Graph Engine.

The `impulse-kotlin` module provides idiomatic Kotlin wrappers, type-safe query building DSLs, extension functions, operator overloading, value classes, and Coroutines support for zero-copy off-heap query execution over immutable binary snapshots (`.imps`).

---

## 1. Installation & Dependency Setup

Add `impulse-kotlin` to your project dependencies:

=== "Gradle (Kotlin DSL)"

    ```kotlin
    dependencies {
        implementation("io.impulse.graph:impulse-kotlin:2.3.0-SNAPSHOT")
        implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
    }
    ```

=== "Maven (`pom.xml`)"

    ```xml
    <dependency>
        <groupId>io.impulse.graph</groupId>
        <artifactId>impulse-kotlin</artifactId>
        <version>2.3.0-SNAPSHOT</version>
    </dependency>
    <dependency>
        <groupId>org.jetbrains.kotlinx</groupId>
        <artifactId>kotlinx-coroutines-core</artifactId>
        <version>1.9.0</version>
    </dependency>
    ```

---

## 2. Idiomatic Query Builder DSL (`impulseQuery`)

Construct type-safe `ImpulseGraphQuery` AST pipelines using `impulseQuery`:

```kotlin
import org.impulsegraph.api.ArgType
import org.impulsegraph.api.ReturnType
import org.impulsegraph.kotlin.impulseQuery

// Define a 2-hop traversal query with bitset collection
val userRolesQuery = impulseQuery<Any> {
    input("USER", ArgType.SINGLE_ID)
    walkEdge "userToGroup"
    walkTarget "GROUP"
    walkEdge "groupToRole"
}.collect<Any>(ReturnType.ROARING_BITSET)
```

### Infix Steps & Attribute Filtering

```kotlin
val lineLoadQuery = impulseQuery<Double> {
    input("Load", ArgType.SINGLE_ID)
    walkEdgeFilteredAttribute("powerLine", "voltage", ">", 110.0)
    filterNodeAttribute("current", "<=", 50.0)
    projectExpression("voltage", "*", "current")
}.reduceSum<Double>()
```

### Fixed & Convergent Loops (`repeat` / `repeatUntilStable`)

```kotlin
// Fixed N-hop traversal loop
val fourHopQuery = impulseQuery<Any> {
    input("USER", ArgType.SINGLE_ID)
    repeat(4) {
        walkEdge "friend"
    }
}.collect<Any>(ReturnType.ROARING_BITSET)

// Convergent transitive closure loop
val closureQuery = impulseQuery<Any> {
    input("USER", ArgType.SINGLE_ID)
    repeatUntilStable {
        walkEdge "memberOf"
    }
}.collect<Any>(ReturnType.ROARING_BITSET)
```

---

## 3. Operator Overloading & Extension Functions

`impulse-kotlin` adds standard Kotlin operators to query objects and snapshot instances:

### Query Execution Operators

```kotlin
import org.impulsegraph.kotlin.invoke
import org.impulsegraph.kotlin.execute

// Operator overloading allows queries to be called as functions:
val result = userRolesQuery(snapshot, seedUserId)

// Extension function style:
val result2 = snapshot.execute(userRolesQuery, seedUserId)
```

### Snapshot Indexing & Properties

```kotlin
import org.impulsegraph.kotlin.get
import org.impulsegraph.kotlin.contains
import org.impulsegraph.kotlin.size

// Array indexing access for edge counts
val edgeCount: Long = snapshot["userToGroup"]

// Check relation existence using the 'in' operator
if ("groupToRole" in snapshot) {
    println("Relation present in snapshot")
}

// Relation count property shorthand
println("Total relations: ${snapshot.size}")
```

---

## 4. Kotlin Coroutines Async Execution

Execute off-heap traversals asynchronously without blocking worker threads:

```kotlin
import kotlinx.coroutines.Dispatchers
import org.impulsegraph.kotlin.executeAsync
import org.impulsegraph.kotlin.awaitDrainedAsync

suspend fun fetchUserRoles(snapshot: ImpulseGraphSnapshot, userId: Long): RoaringBitmap {
    // Executes query on Dispatchers.IO asynchronously
    return snapshot.executeAsync(userRolesQuery, userId, dispatcher = Dispatchers.IO)
}

suspend fun safeShutdown(snapshot: ImpulseGraphSnapshot) {
    // Await query draining without blocking
    val drained = snapshot.awaitDrainedAsync(timeout = 5L)
    if (drained) {
        snapshot.close()
    }
}
```

---

## 5. Value Classes & Domain Helpers

### Zero-Allocation Inline Value Classes

```kotlin
import org.impulsegraph.kotlin.NodeId
import org.impulsegraph.kotlin.RelationName

val userId = NodeId(10492L)
val relName = RelationName("userToGroup")
```

### Relationship-Based Access Control (ReBAC) DSL Helper

```kotlin
import org.impulsegraph.kotlin.buildRebacQuery

// Construct fine-grained authorization query
val authzQuery = buildRebacQuery(
    entityType = "Document",
    relationName = "owner",
    permission = "edit"
)

val canEdit: Boolean = authzQuery(snapshot, docId)
```

---

## 6. Architecture: Kotlin/JVM vs Kotlin/Native SIMD

| Aspect | Kotlin/JVM (`impulse-kotlin`) | Kotlin/Native |
| :--- | :--- | :--- |
| **Execution Core** | Java 25 Foreign Function & Memory (FFM) + `jdk.incubator.vector` | C-ABI `cinterop` linking `libimpulse_graph` |
| **SIMD Intrinsics** | Hardware-vectorized via Java 25 Vector API (`AVX-512`, `AVX2`, `NEON`) | Executed inside C++20 / Rust C-ABI binary kernel |
| **Memory Access** | Direct zero-copy off-heap `MemorySegment` | Direct off-heap C pointers (`CPointer<T>`) |
| **Garbage Collection** | Zero GC allocation during off-heap `ImpulseVM` traversals | Zero GC allocation in native C heap |
