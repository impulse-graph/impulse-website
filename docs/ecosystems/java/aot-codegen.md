# Schema-First Development & AOT Code Generation

!!! info "Version Note: v0.11 Tooling Suite"
    `SchemaYamlCodec`, `SnapshotSchemaExtractor`, `SnapshotContractValidator`, and `impulse-codegen` v2 (`GeneratorMain` / `SchemaCodeEmitter`) ship in **`v0.11`** (`0.11.0`). Generated source files have **zero third-party dependencies**—they import exclusively `java.*` and `org.impulsegraph.*`.

In stringly-typed graph APIs, three classes of bugs routinely escape into production:

1. **Cross-Domain Dense ID Confusion**: Passing `Account` dense ID `0` into a `User` traversal (`snap.domain("User").from(accountDenseId)`), silently traversing an unrelated entity because every domain independently indexes $0 \dots N_d - 1$.
2. **Invalid Direction or Typo Bugs**: Calling `.in("USER_POSTS_POST")` on a forward-only relation built without a reverse `CSC` index, or misspelling an attribute name inside a CEL string (`"reputaton >= 50"`).
3. **Producer/Consumer Drift**: Mounting a newly rebuilt `.imps` snapshot where an upstream pipeline dropped an attribute or widened a non-null column to nullable.

`impulse-codegen` eliminates all three failure modes at **`javac` compile time** and **snapshot mount time** by compiling a declarative [`.imps.schema.yaml`](../../reference/spec/schema-specification.md) contract into strongly-typed, zero-allocation Java 21+ classes.

---

## 1. Authoring or Extracting `.imps.schema.yaml`

### Authoring a Schema Contract Forward

Create `src/main/resources/schema.yaml` (or `bank.imps.schema.yaml`):

```yaml
package: com.example.bank.graph
graphName: BankGraph
version: "1.2.0"

domains:
  User:
    idWidth: uint32
    keyType: uuid
    attributes:
      username: { type: fixed_string, dimension: 32, nullable: false, indexed: true }
      risk_score: { type: int32, nullable: false }
      kyc_tier: { type: int32, optional: true, since: "1.2.0" }
      embedding: { type: "float32[128]", nullable: false }

  Account:
    idWidth: uint32
    keyType: int64
    attributes:
      balance: { type: float64, nullable: false }
      frozen_reason: { type: var_string, nullable: true }

relations:
  owns:
    source: User
    target: Account
    directions: [out, in]
    inverseAlias: ownedBy
    cardinality: one_to_many

  transferredTo:
    source: Account
    target: Account
    directions: [out]          # Forward CSR only — no reverse CSC index
    cardinality: many_to_many
    attributes:
      amount: { type: float64, nullable: false }
```

You can parse and validate any schema manifest programmatically using `SchemaYamlCodec` and `SchemaValidator` in `impulse-api` (zero external YAML libraries required):

```java
import org.impulsegraph.api.schema.GraphManifest;
import org.impulsegraph.api.schema.SchemaValidator;
import org.impulsegraph.api.schema.SchemaYamlCodec;

import java.nio.file.Path;
import java.util.List;

GraphManifest manifest = SchemaYamlCodec.parse(Path.of("src/main/resources/schema.yaml"));
List<String> errors = SchemaValidator.validate(manifest);
if (!errors.isEmpty()) {
    throw new IllegalArgumentException("Invalid schema: " + errors);
}
String sha256 = manifest.schemaFingerprintSha256(); // Deterministic canonical YAML SHA-256
```

### Reverse-Extracting a Schema from an Existing `.imps` Snapshot

If a Python or Rust pipeline already produces an `.imps` file, reconstruct its canonical `.imps.schema.yaml` via [`impulse-j schema extract`](cli-impulse-j.md), [`impulse-maven-plugin:extract-schema`](maven-and-build-tooling.md), or `SnapshotSchemaExtractor`:

```java
import org.impulsegraph.storage.csr.BinarySnapshotLoader;
import org.impulsegraph.storage.schema.SnapshotSchemaExtractor;

import java.lang.foreign.Arena;
import java.nio.file.Path;

try (Arena arena = Arena.ofConfined();
     BinarySnapshotLoader.LoadedSnapshot loaded =
             BinarySnapshotLoader.loadSnapshot(Path.of("datasets/bank_graph.imps"), arena)) {

    String canonicalYaml = SnapshotSchemaExtractor.extractYaml(loaded);
    System.out.println(canonicalYaml);
}
```

`GeneratorMain.generate(...)` also accepts an `.imps` file directly as its input path, performing reverse extraction and Java source emission in one step.

---

## 2. Running `impulse-codegen`

In standard builds, configure [`impulse-maven-plugin:generate`](maven-and-build-tooling.md) so generated sources are compiled automatically during `generate-sources`. You can also invoke `GeneratorMain` via [`impulse-j codegen`](cli-impulse-j.md) or Java code:

```java
import org.impulsegraph.codegen.GeneratorMain;
import java.nio.file.Path;

GeneratorMain.generate(
        Path.of("src/main/resources/schema.yaml"),
        Path.of("target/generated-sources/impulse"),
        null // Uses 'package:' from schema.yaml, or overrides if non-null
);
```

---

## 3. Complete Catalog of Generated Artifacts

For the `BankGraph` schema above, `SchemaCodeEmitter` emits the following classes into `com.example.bank.graph`:

| Generated Class | Role & Compile-Time / Runtime Guarantees |
| :--- | :--- |
| **`UserId`**, **`AccountId`** | Distinct Java `record` wrappers (`record UserId(long denseId)`) enforcing `denseId >= 0`. Passing an `AccountId` to `snap.users().from(...)` is a **`javac` compile error**. |
| **`BankGraphSnapshot`** | AutoCloseable typed facade embedding `SCHEMA_YAML` & `SCHEMA`. `open(Path, Arena)` mounts the `.imps` file and runs `SnapshotContractValidator.validateAndBind(...)` upfront, pre-resolving off-heap `BoundSchemaHandles`. Provides `users()`, `accounts()`, and `createLifecycleManager(...)`. |
| **`UserDomainView`**, **`AccountDomainView`** | Domain entrypoints parameterized by the domain's `keyType`: `UserDomainView` exposes `fromKey(UUID)`, `toDenseId(UUID)`, `toKey(long) -> UUID`, `hasKycTier()`, and `vectorSearchEmbedding(float[], int)` (enforcing `length == 128`). `AccountDomainView` exposes `fromKey(long)` and `toKey(long) -> long`. |
| **`UserTraversal`**, **`AccountTraversal`** | Kleisli frontier builders whose edge methods transition the static return type across domains: `UserTraversal.outOwns()` returns `AccountTraversal`. Reverse methods (`inOwns()`, `ownedBy()`) are emitted **only** when `directions` includes `in` (or `symmetric: true`)—`inTransferredTo()` is not generated because `transferredTo` is `[out]`-only! |
| **`UserAttrs`**, **`UserPredicate`**, **`AccountAttrs`**, **`AccountPredicate`** | Type-safe CEL node attribute metamodel (`IntAttr`, `LongAttr`, `DoubleAttr`, `BoolAttr`, `StringAttr`, `BytesAttr`) with automatic string escaping and `.and(...)` / `.or(...)` / `.not()` composition. |
| **`TransferredToEdgeAttrs`**, **`TransferredToEdgePredicate`** | Emitted for relations with edge attributes (`TransferredToEdgeAttrs.AMOUNT.gt(1000.0)`), accepted by `AccountTraversal.outTransferredTo(TransferredToEdgePredicate)`. |
| **`UserRowView`**, **`AccountRowView`** | **Zero-allocation flyweight off-heap cursors** reused across `forEachRow(Consumer<AccountRowView>)`. Reads little-endian primitives, UTF-8 strings, validity bitmasks (`isFrozenReasonNull()`), optional guards (`hasKycTier()`, `kycTierOrDefault(0)`), and reusable vector buffers (`embedding(float[] dest)`) directly from pre-bound `MemorySegment` slices. |
| **`UserRecord`**, **`AccountRecord`** | Immutable boundary Java `record` DTOs materialized via `row.toRecord()` or `traversal.toRecords()`. Non-null columns map to primitives (`double balance`); nullable or `optional: true` columns map to boxed types (`String frozenReason`, `Integer kycTier`). |
| **`BankGraphSnapshotWriter`** | Typed streaming builder wrapper (`domainUser(...)`, `domainAccount(...)`, `relationOwns(...)`, `relationTransferredTo(...)`) that automatically configures `PrimitiveWidth`, `Topology.CSC`, and `impulse.schema.*` footer provenance. |

---

## 4. Before vs. After: Stringly-Typed vs. Schema-First AOT

=== "After: Schema-First AOT (`impulse-codegen`)"

    ```java
    import com.example.bank.graph.AccountAttrs;
    import com.example.bank.graph.AccountRecord;
    import com.example.bank.graph.BankGraphSnapshot;
    import com.example.bank.graph.TransferredToEdgeAttrs;

    import java.lang.foreign.Arena;
    import java.nio.file.Path;
    import java.util.List;
    import java.util.UUID;

    UUID userUuid = UUID.fromString("00000000-0000-0000-0000-000000000101");

    try (Arena arena = Arena.ofShared();
         // Validates entire schema contract & pre-binds MemorySegment handles at open time!
         BankGraphSnapshot snap = BankGraphSnapshot.open(Path.of("datasets/bank.imps"), arena)) {

        // 1. Domain-transitioning Kleisli pipeline:
        //    users() [UserDomainView]
        //      -> fromKey(UUID) [UserTraversal]
        //      -> outOwns() [AccountTraversal]
        //      -> outTransferredTo(EdgePredicate) [AccountTraversal]
        //      -> where(AccountPredicate) [AccountTraversal]
        var suspectAccounts = snap.users()
                .fromKey(userUuid)
                .outOwns()
                .outTransferredTo(TransferredToEdgeAttrs.AMOUNT.gt(10_000.0))
                .where(AccountAttrs.BALANCE.ge(50_000.0)
                        .and(AccountAttrs.FROZEN_REASON.isNull()));

        // 2. Zero-allocation off-heap iteration via reusable AccountRowView flyweight:
        suspectAccounts.forEachRow(row -> {
            long accountDenseId = row.denseId();
            double balance = row.balance(); // Direct MemorySegment LE_DOUBLE read
            // Process in-place without allocating per-row heap objects...
        });

        // 3. Or materialize typed external keys (List<Long>) / boundary DTOs (List<AccountRecord>):
        List<Long> accountKeys = suspectAccounts.toKeyList();
        List<AccountRecord> records = suspectAccounts.toRecords();
    }
    ```

=== "Before: Raw Stringly-Typed Core API"

    ```java
    import org.impulsegraph.api.ImpulseGraphSnapshot;
    import org.impulsegraph.storage.csr.BinarySnapshotLoader;

    import java.lang.foreign.Arena;
    import java.nio.file.Path;
    import java.util.List;

    try (Arena arena = Arena.ofShared();
         BinarySnapshotLoader.LoadedSnapshot loaded =
                 BinarySnapshotLoader.loadSnapshot(Path.of("datasets/bank.imps"), arena)) {

        ImpulseGraphSnapshot snap = loaded.graph();

        // Domain names, relation names, key formatting, and CEL identifiers are
        // verified only when the query executes at runtime:
        List<String> rawKeys = snap.domain("User")
                .fromKey("00000000-0000-0000-0000-000000000101")
                .out("owns")
                .out("transferredTo", "edge.amount > 10000.0")
                .filter("balance >= 50000.0 && isNull(frozen_reason)")
                .toKeyList();

        List<Long> accountKeys = rawKeys.stream().map(Long::valueOf).toList();
    }
    ```

---

## 5. Zero-Allocation Flyweight `RowView` & Evolution Guards

Inside `<Domain>RowView`, `SchemaCodeEmitter` binds `MemorySegment` references (`dataSeg`, `validitySeg`, `offsetsSeg`) once from `BoundSchemaHandles` before iterating the surviving `ImpulseBitSet` frontier:

* **Zero Heap Churn on Vectors**: For `embedding: { type: "float32[128]" }`, `UserRowView` generates `void embedding(float[] dest)`, allowing a single caller-allocated `float[128]` array to be reused across millions of visited nodes without allocating `float[]` arrays per node.
* **Safe Rolling Evolution (`optional: true` / `since`)**: Attributes marked `optional: true` or carrying a `since:` version tag allow your new consumer code to mount older `.imps` snapshots where that column does not yet exist. Generated `UserDomainView.hasKycTier()`, `UserRowView.hasKycTier()`, and `row.kycTierOrDefault(0)` let application code branch cleanly without `NullPointerException` or bounds traps, while calling bare `row.kycTier()` when absent fails fast with a descriptive `IllegalStateException`.
* **`@Deprecated` Propagation**: Adding `deprecated: "Use kyc_tier"` to any domain, attribute, relation, or virtual relation in `.imps.schema.yaml` automatically emits `@Deprecated` on the corresponding generated Java methods so IDEs and `-Werror` builds flag stale usages immediately.

---

## Next Steps

* **[Maven Plugin & Build-Time AOT Pipeline](maven-and-build-tooling.md)** — Run `impulse:generate` and `impulse:aot-compile` automatically during `mvn compile`.
* **[Day-2 Operations: Kubernetes, Hot-Swap Lifecycle & Schema Evolution](kubernetes-and-lifecycle.md)** — Pair `BankGraphSnapshot.createLifecycleManager(...)` with zero-downtime epoch swaps.
