# Scala 3 API Reference (`impulse-scala_3`)

Welcome to the **Scala 3 Extensions & Idiomatic DSL API Reference** for the Impulse Graph Engine.

The `impulse-scala_3` library provides idiomatic Scala 3 wrappers, quiet syntax query building DSLs, extension methods, zero-cost opaque type aliases, and `scala.concurrent.Future` async execution over off-heap binary snapshots (`.imps`).

---

## 1. Installation & Dependency Setup

Add `impulse-scala_3` to your project build definition:

=== "sbt (`build.sbt`)"

    ```scala
    libraryDependencies += "io.impulse.graph" %% "impulse-scala" % "2.3.0-SNAPSHOT"
    ```

=== "Maven (`pom.xml`)"

    ```xml
    <dependency>
        <groupId>io.impulse.graph</groupId>
        <artifactId>impulse-scala_3</artifactId>
        <version>2.3.0-SNAPSHOT</version>
    </dependency>
    ```

---

## 2. Idiomatic Query Builder DSL (`impulseQuery`)

Construct type-safe `ImpulseGraphQuery` AST pipelines using `impulseQuery` in Scala 3 quiet syntax:

```scala
import org.impulsegraph.api.{ArgType, ReturnType}
import org.impulsegraph.scala.impulseQuery

// Define a 2-hop traversal query with bitset collection
val userRolesQuery = impulseQuery[Any] { dsl =>
  dsl.input("USER", ArgType.SINGLE_NODE)
  dsl.walkEdge("userToGroup")
  dsl.walkTarget("GROUP")
  dsl.walkEdge("groupToRole")
}.collect[Any](ReturnType.ROARING_BITSET)
```

### Attribute Filtering & Reductions

```scala
val lineLoadQuery = impulseQuery[java.lang.Double] { dsl =>
  dsl.input("Load", ArgType.SINGLE_NODE)
  dsl.walkEdgeFilteredAttribute("powerLine", "voltage", ">", 110.0)
  dsl.filterNodeAttribute("current", "<=", 50.0)
  dsl.projectExpression("voltage", "*", "current")
}.reduceSum[java.lang.Double]()
```

### Fixed & Convergent Loops (`repeat` / `repeatUntilStable`)

```scala
// Fixed N-hop traversal loop
val fourHopQuery = impulseQuery[Any] { dsl =>
  dsl.input("USER", ArgType.SINGLE_NODE)
  dsl.repeat(4) { subDsl =>
    subDsl.walkEdge("friend")
  }
}.collect[Any](ReturnType.ROARING_BITSET)
```

---

## 3. Extension Methods & Apply Operators

`impulse-scala` uses Scala 3 `extension` clauses to enhance core Java API types:

### Query Execution & Indexing

```scala
import org.impulsegraph.scala.*

// Function invocation syntax via apply overload:
val result = userRolesQuery(snapshot, seedUserId)

// Extension method on ImpulseGraphSnapshot:
val result2 = snapshot.execute(userRolesQuery, seedUserId)

// Apply indexing access for edge counts:
val edgeCount: Long = snapshot("userToGroup")

// Relation existence check:
if snapshot.containsRelation("groupToRole") then
  println("Relation present in snapshot")
```

---

## 4. Asynchronous Query Execution (`Future`)

Execute off-heap traversals asynchronously via standard Scala `Future`:

```scala
import scala.concurrent.{ExecutionContext, Future}
import org.impulsegraph.scala.*

def fetchUserRolesAsync(snapshot: ImpulseGraphSnapshot, userId: Long)(using ec: ExecutionContext): Future[RoaringBitmap] =
  snapshot.executeAsync(userRolesQuery, userId.asInstanceOf[AnyRef])
```

---

## 5. Opaque Type Aliases & Domain Helpers

### Zero-Allocation Opaque Types

Scala 3 `opaque type` declarations enforce compile-time type safety for node IDs and relation names with zero runtime allocation overhead:

```scala
import org.impulsegraph.scala.DomainTypes.*

val userId: NodeId = NodeId(10492L)
val relName: RelationName = RelationName("userToGroup")

// Access underlying primitives
val rawId: Long = userId.value
```

### ReBAC Permission Check DSL

```scala
import org.impulsegraph.scala.buildRebacQuery

// Build Relationship-Based Access Control query
val authzQuery = buildRebacQuery(
  entityType = "Document",
  relationName = "owner",
  permission = "edit"
)

val canEdit: java.lang.Boolean = authzQuery(snapshot, docId)
```

---

## 6. Resource Management (`scala.util.Using`)

Manage off-heap memory-mapped snapshot lifecycles safely:

```scala
import scala.util.Using

Using.resource(BinarySnapshotLoader.loadSnapshot(path, arena).graph()) { snapshot =>
  val result = userRolesQuery(snapshot, seedId)
  println(s"Query executed successfully over ${snapshot.size} relations")
}
```
