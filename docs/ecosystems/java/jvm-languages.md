# Kotlin, Scala 3, Clojure & Java API Reference

Because `impulse-api` exposes clean Java interfaces without checked exceptions on traversal pipelines and `impulse-codegen` emits standard Java 21+ classes and `record` types, **Kotlin**, **Scala 3**, and **Clojure** applications can combine AOT-generated typed facades directly with Impulse's idiomatic JVM language extension modules (`0.10.1` on Maven Central; aligned via `impulse-bom` in `0.11.0`).

---

## 1. Kotlin (`org.impulsegraph:impulse-kotlin`)

`impulse-kotlin` provides `@JvmInline` value classes (`NodeId`, `RelationName`), `ImpulseSnapshots.withSnapshot`, operator overloads, `Sequence<Int>` bitset adapters, `@ImpulseQueryDslMarker` query builders, and **Kotlin Coroutines** `suspend` wrappers (`executeAsync`, `awaitDrainedAsync`, `drainAndCloseAsync`).

### Dependency

```kotlin
dependencies {
    implementation(platform("org.impulsegraph:impulse-bom:$impulseVersion"))
    implementation("org.impulsegraph:impulse-kotlin")
    implementation("org.impulsegraph:impulse-storage")
    implementation("org.impulsegraph:impulse-vm")
    implementation("org.impulsegraph:impulse-compiler")
}
```

### Pairing Kotlin with AOT-Generated Classes & Coroutines

```kotlin
import com.example.bank.graph.AccountAttrs
import com.example.bank.graph.BankGraphSnapshot
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.impulsegraph.api.bitset.ImpulseBitSet
import org.impulsegraph.kotlin.NodeId
import org.impulsegraph.kotlin.RelationName
import org.impulsegraph.kotlin.asSequence
import org.impulsegraph.kotlin.executeAsync
import org.impulsegraph.kotlin.impulseQuery
import java.lang.foreign.Arena
import java.nio.file.Path
import java.util.UUID

// 1. Reusable compiled DSL pipeline using @JvmInline NodeId & RelationName
val twoHopReachability = impulseQuery<ImpulseBitSet> {
    input("Account", NodeId(0L))
    repeat(2) {
        walkEdge(RelationName("transferredTo"))
    }
    filterWithCel("balance >= 10000.0")
}.collectBitSet()

// 2. Suspend function combining AOT-generated BankGraphSnapshot + Coroutine execution
suspend fun inspectSuspectAccounts(impsFile: Path, userUuid: UUID): List<Long> =
    withContext(Dispatchers.IO) {
        Arena.ofShared().use { arena ->
            BankGraphSnapshot.open(impsFile, arena).use { snap ->
                // Schema-typed Kleisli traversal + CEL metamodel
                val ownedHighBalance = snap.accounts()
                    .from(
                        snap.users()
                            .fromKey(userUuid)
                            .outOwns()
                            .toBitSet()
                    )
                    .where(AccountAttrs.BALANCE.ge(25_000.0))
                    .toKeyList()

                // Or execute pre-built Kotlin DSL query asynchronously on underlying snapshot
                val reachableBits = snap.underlying().executeAsync(twoHopReachability, input = 0L)
                val reachableCount = reachableBits.asSequence().count()

                ownedHighBalance
            }
        }
    }
```

---

## 2. Scala 3 (`org.impulsegraph:impulse-scala_3`)

`impulse-scala_3` uses Scala 3 **opaque types** (`opaque type NodeId = Long`, `opaque type RelationName = String`), **context functions** (`ImpulseQueryDsl[R] ?=> Unit`) for receiver-less DSL blocks, `Using` / `Try` resource management, and `scala.concurrent.Future` (`executeAsync`).

### Dependency (`build.sbt`)

```scala
libraryDependencies ++= Seq(
  "org.impulsegraph" % "impulse-scala_3"  % impulseVersion,
  "org.impulsegraph" % "impulse-storage"  % impulseVersion,
  "org.impulsegraph" % "impulse-vm"       % impulseVersion,
  "org.impulsegraph" % "impulse-compiler" % impulseVersion
)
```

### Scala 3 Context-Function DSL & AOT Interop

```scala
import com.example.bank.graph.{AccountAttrs, BankGraphSnapshot}
import org.impulsegraph.api.bitset.ImpulseBitSet
import org.impulsegraph.scala.*
import java.lang.foreign.Arena
import java.nio.file.Path
import java.util.UUID
import scala.jdk.CollectionConverters.*
import scala.util.Using

// 1. Receiver-less Scala 3 context-function query definition
val transitiveTransfers = impulseQuery[ImpulseBitSet] {
  input("Account", NodeId(0L))
  repeatUntilStable {
    walkEdge(RelationName("transferredTo"))
  }
  filter("balance >= 5000.0")
}.collectBitSet()

// 2. Safe Arena + AOT facade management with scala.util.Using
def activeAccountKeys(impsPath: Path, userId: UUID): List[Long] =
  Using.Manager { use =>
    val arena = use(Arena.ofShared())
    val snap  = use(BankGraphSnapshot.open(impsPath, arena))

    // Execute Scala 3 DSL query on the underlying snapshot:
    val reachableSet: Set[Int] = snap.underlying()(transitiveTransfers, 0L).toScalaSet

    // Combine with AOT-generated typed traversal:
    snap.users()
      .fromKey(userId)
      .outOwns()
      .where(AccountAttrs.FROZEN_REASON.isNull())
      .toKeyList()
      .asScala
      .map(_.longValue())
      .toList
  }.get
```

---

## 3. Clojure (`org.impulsegraph:impulse-clojure`)

Because `ImpulseVM`'s canonical compiler IR (`ImpScheme`) is an S-expression AST, Clojure integrates naturally as a homoiconic frontend (`org.impulsegraph.core`). `SnapshotWrapper` implements Clojure's `ILookup` (`(:owns snap)` returns the relation's edge count), `Counted` (`(count snap)`), `IDeref` (`@snap`), and `IImpulseSnapshot`.

### Dependency (`deps.edn`)

```clojure
{:deps {org.impulsegraph/impulse-clojure  {:mvn/version "0.10.1"}
        org.impulsegraph/impulse-storage  {:mvn/version "0.10.1"}
        org.impulsegraph/impulse-vm       {:mvn/version "0.10.1"}
        org.impulsegraph/impulse-compiler {:mvn/version "0.10.1"}}
 :aliases {:run {:jvm-opts ["--add-modules" "jdk.incubator.vector"
                            "--enable-native-access=ALL-UNNAMED"]}}}
```

### Homoiconic Pipeline, `defquery` & Prepared Statements

```clojure
(ns example.bank
  (:refer-clojure :exclude [in])
  (:require [org.impulsegraph.core :as imp]))

;; Define a reusable domain-bound Kleisli pipeline via defquery:
(imp/defquery suspect-recipients [snap domain seed]
  (imp/out :owns)
  (imp/out-filtered :transferredTo "edge.amount > $minAmount")
  (imp/filter-nodes "balance >= 50000.0")
  (imp/with-param :minAmount 10000.0))

(imp/with-snapshot [snap "datasets/bank.imps"]
  ;; Keyword lookup on SnapshotWrapper returns edge count:
  (println "OWNS edges:" (:owns snap) "Domains:" (imp/domain-names snap))

  ;; Inspect emitted ImpScheme S-Expression IR or materialize persistent set:
  (let [pipeline (suspect-recipients snap :User 0)]
    (println "ImpScheme IR:" (imp/to-scm-string pipeline))
    (println "Matching Account Dense IDs:" (imp/to-set pipeline)))

  ;; Parameterized openCypher prepared statement:
  (imp/with-statement [stmt snap
                       "MATCH (u:User)-[:owns]->(a:Account) WHERE a.balance >= $min RETURN a"]
    (imp/bind-params stmt {:min 25000.0})
    (with-open [rows (.execute stmt)]
      (loop [acc []]
        (if (.next rows)
          (recur (conj acc (.getNodeId rows 0)))
          acc)))))
```

---

## 4. Core Java SDK Reference & Aggregated Javadocs

For low-level Java engine interfaces—including `ImpulseStatement` / `RowReader`, monoidic state reducers (`:MIN`, `:MAX`, `:SUM`, `:AVG`, `:ARGMIN`, `:ARGMAX`), and Multi-Lane Bit-Sliced Execution (`VmLaneFrontier`, `0xC0..0xCB`)—see:

* **[Java SDK Reference (`impulse-graph-java`)](../../reference/java-api.md)**
* **[Interactive Multi-Module Javadocs (`/javadoc/index.html`)](/javadoc/index.html)**
