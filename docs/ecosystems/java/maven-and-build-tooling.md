# Maven Plugin & Build-Time AOT Pipeline

!!! info "Version Note: v0.11 Tooling Suite"
    The 7-Mojo `org.impulsegraph:impulse-maven-plugin` suite (`generate`, `generate-test`, `aot-compile`, `build-snapshot`, `extract-schema`, `validate`, `check-compat`) ships in **`v0.11`** (`0.11.0`). In `0.10.0` on Maven Central, only the baseline `generate` goal is published.

`impulse-maven-plugin` (goal prefix **`impulse`**) integrates schema-first Java code generation, snapshot-agnostic build-time query verification, deterministic `.imps` test fixture building, and multi-consumer compatibility gating directly into the standard Maven build lifecycle.

---

## 1. Summary of All 7 Maven Goals

| Goal (`impulse:<goal>`) | Mojo Class | Default Lifecycle Phase | Key `<configuration>` Parameters | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **`impulse:generate`** | `GenerateQueryBuildersMojo` | `generate-sources` | `schemaFile`, `outputDirectory`, `packageName`, `skipIfMissing` | Generates typed Java snapshot facades, `<Domain>Id` records, traversals, CEL metamodels, `RowView` cursors, and writers; registers compile source root. |
| **`impulse:generate-test`** | `GenerateTestQueryBuildersMojo` | `generate-test-sources` | `schemaFile`, `outputDirectory`, `packageName`, `skipIfMissing` | Generates typed Java classes from a test schema and registers `target/generated-test-sources/impulse` as a test compile root. |
| **`impulse:aot-compile`** | `AotCompileQueriesMojo` | `generate-sources` | `queriesDirectory`, `schemaFile`, `outputDirectory`, `skipIfMissing` | Lowers `.cypher`, `.impk`, `.implog`, and `.impscm` query files, validates all domain/relation/direction/attribute references via `SchemaBindValidatorPass`, and emits normalized `.impscm` IR resources. |
| **`impulse:build-snapshot`** | `BuildSnapshotMojo` | `generate-test-resources` | `manifestFile` *(req)*, `outputFile` *(req)*, `skipIfMissing` | Compiles a CSV/TSV/JSONL `manifest.yaml` or `manifest.json` into an immutable `.imps` binary snapshot in pure Java. |
| **`impulse:extract-schema`** | `ExtractSchemaMojo` | *(CLI / explicit)* | `snapshotFile` *(req)*, `outputFile` *(req)* | Reverse-extracts a canonical `.imps.schema.yaml` file from an existing `.imps` binary snapshot. |
| **`impulse:validate`** | `ValidateSnapshotMojo` | `verify` | `snapshotFile` *(req)*, `schemaFile`, `strictAlignment`, `deepAudit`, `quickCheck` | Audits `.imps` Page 0 header, 128B alignment, CSR monotonicity, CSC transpose multiset, SHA-256 digest, and optional consumer schema conformance. |
| **`impulse:check-compat`** | `CheckCompatMojo` | `verify` | `snapshotFile` *(req)*, `consumerSchemas` *(req)* | CI producer gate: validates a candidate `.imps` file against a list of downstream consumer `.imps.schema.yaml` contracts, failing `mvn verify` on any breaking change. |

### Exact Parameter Reference & System Properties

| Goal(s) | XML Tag | `-D` User Property | Default Value |
| :--- | :--- | :--- | :--- |
| `generate` | `<schemaFile>` | `-Dimpulse.schemaFile` | `${project.basedir}/src/main/resources/schema.yaml` |
| `generate` | `<outputDirectory>` | `-Dimpulse.outputDirectory` | `${project.build.directory}/generated-sources/impulse` |
| `generate` | `<packageName>` | `-Dimpulse.packageName` | `org.impulsegraph.generated` *(if `package:` omitted in YAML)* |
| `generate-test` | `<schemaFile>` | `-Dimpulse.testSchemaFile` | `${project.basedir}/src/test/resources/schema.yaml` |
| `generate-test` | `<outputDirectory>` | `-Dimpulse.testOutputDirectory` | `${project.build.directory}/generated-test-sources/impulse` |
| `generate-test` | `<packageName>` | `-Dimpulse.testPackageName` | `org.impulsegraph.generated.test` |
| `aot-compile` | `<queriesDirectory>` | `-Dimpulse.queriesDirectory` | `${project.basedir}/src/main/impulse/queries` |
| `aot-compile` | `<outputDirectory>` | `-Dimpulse.aotOutputDirectory` | `${project.build.directory}/generated-resources/impulse/queries` |
| `build-snapshot` | `<manifestFile>` | `-Dimpulse.manifestFile` | *(Required)* |
| `build-snapshot`, `extract-schema` | `<outputFile>` | `-Dimpulse.outputFile` | *(Required)* |
| `extract-schema`, `validate`, `check-compat` | `<snapshotFile>` | `-Dimpulse.snapshotFile` | *(Required)* |
| `validate` | `<strictAlignment>` / `<deepAudit>` / `<quickCheck>` | `-Dimpulse.strictAlignment` / `-Dimpulse.deepAudit` / `-Dimpulse.quickCheck` | `false` |
| `generate`, `generate-test`, `aot-compile`, `build-snapshot` | `<skipIfMissing>` | `-Dimpulse.skipIfMissing` | `false` |

---

## 2. Recipe 1: Schema-First AOT Source Generation & IDE Integration

Bind `generate` (and optionally `generate-test`) in your microservice `pom.xml`:

```xml
<plugin>
    <groupId>org.impulsegraph</groupId>
    <artifactId>impulse-maven-plugin</artifactId>
    <version>${impulse.version}</version>
    <executions>
        <execution>
            <id>generate-main-graph-api</id>
            <goals>
                <goal>generate</goal>
            </goals>
            <configuration>
                <schemaFile>${project.basedir}/src/main/resources/bank.imps.schema.yaml</schemaFile>
                <outputDirectory>${project.build.directory}/generated-sources/impulse</outputDirectory>
                <packageName>com.example.bank.graph</packageName>
            </configuration>
        </execution>
    </executions>
</plugin>
```

### Automatic IntelliJ IDEA & Eclipse `m2e` Source-Root Registration

`impulse-maven-plugin` embeds `META-INF/m2e/lifecycle-mapping-metadata.xml` with `<runOnIncremental>true</runOnIncremental>` and `<runOnConfiguration>true</runOnConfiguration>` for `generate`, `generate-test`, `aot-compile`, and `build-snapshot`, and invokes `project.addCompileSourceRoot(...)` / `project.addTestCompileSourceRoot(...)` directly.

Importing or reloading the Maven project in **IntelliJ IDEA**, **Eclipse (`m2e`)**, or **VS Code Java** automatically marks `target/generated-sources/impulse` as a generated source root without requiring `build-helper-maven-plugin`.

---

## 3. Recipe 2: Build-Time Query Verification (`impulse:aot-compile`)

If your team maintains standalone `.cypher`, `.impk`, `.implog`, or `.impscm` query files under `src/main/impulse/queries/`, `impulse:aot-compile` catches query bugs during `mvn compile`—**without requiring a multi-gigabyte `.imps` file on the build runner**.

```xml
<plugin>
    <groupId>org.impulsegraph</groupId>
    <artifactId>impulse-maven-plugin</artifactId>
    <version>${impulse.version}</version>
    <executions>
        <execution>
            <id>aot-validate-and-lower-queries</id>
            <goals>
                <goal>aot-compile</goal>
            </goals>
            <configuration>
                <queriesDirectory>${project.basedir}/src/main/impulse/queries</queriesDirectory>
                <schemaFile>${project.basedir}/src/main/resources/bank.imps.schema.yaml</schemaFile>
                <outputDirectory>${project.build.directory}/generated-resources/impulse/queries</outputDirectory>
            </configuration>
        </execution>
    </executions>
</plugin>
```

### What `SchemaBindValidatorPass` Catches at Build Time

During `aot-compile`, each query file is parsed by its frontend compiler (`CypherCompiler`, `ImpKCompiler`, `ImpLogCompiler`, or `ImpScmParser`) into `ImpScheme` AST and checked against `schemaFile` via `SchemaBindValidatorPass`:

* **Unknown Domains, Relations, or Attributes**: e.g., `r.unknown_score > 10` in a `.cypher` file fails `mvn compile` with `MojoFailureException` listing every offending file and AST path.
* **Missing Reverse `CSC` Topology**: Walking backward (`<-[:userPostsPost]-` or `(csc-walk "userPostsPost")`) over a relation declared `directions: [out]` fails the build immediately.
* **CEL Expression Type Mismatches**: Applying arithmetic or boolean operators to incompatible attribute types (such as comparing a `var_string` column with `>` against a numeric literal or applying `&&` to a numeric field).

Validated queries are serialized as normalized `.impscm` S-expression IR files under `target/generated-resources/impulse/queries/`. At service startup (or pre-swap inside `SnapshotLifecycleManager`), `QueryRegistry.validateAndBindAll(snapshot, arena)` performs Stage 2 physical binding to emit snapshot-specific `impOps` bytecode—or use [`impulse-j compile --snapshot ... -o query.impb`](cli-impulse-j.md) when building against a fixed `.imps` artifact.

---

## 4. Recipe 3: Test Fixture Snapshots & Producer CI Compatibility Gates

In a snapshot producer pipeline—or an integration-test module—combine `build-snapshot` (during `generate-test-resources`) with `validate` and `check-compat` (during `verify`):

```xml
<plugin>
    <groupId>org.impulsegraph</groupId>
    <artifactId>impulse-maven-plugin</artifactId>
    <version>${impulse.version}</version>
    <executions>
        <!-- 1. Compile CSV/TSV/JSONL test fixture before JUnit runs -->
        <execution>
            <id>build-test-fixture-snapshot</id>
            <phase>generate-test-resources</phase>
            <goals>
                <goal>build-snapshot</goal>
            </goals>
            <configuration>
                <manifestFile>${project.basedir}/src/test/impulse/manifest.yaml</manifestFile>
                <outputFile>${project.build.directory}/test-snapshots/social.imps</outputFile>
            </configuration>
        </execution>

        <!-- 2. Deep binary & schema audit in mvn verify -->
        <execution>
            <id>audit-built-snapshot</id>
            <phase>verify</phase>
            <goals>
                <goal>validate</goal>
            </goals>
            <configuration>
                <snapshotFile>${project.build.directory}/test-snapshots/social.imps</snapshotFile>
                <schemaFile>${project.basedir}/src/main/resources/producer.imps.schema.yaml</schemaFile>
                <strictAlignment>true</strictAlignment>
                <deepAudit>true</deepAudit>
            </configuration>
        </execution>

        <!-- 3. Multi-consumer structural compatibility gate -->
        <execution>
            <id>verify-downstream-consumers</id>
            <phase>verify</phase>
            <goals>
                <goal>check-compat</goal>
            </goals>
            <configuration>
                <snapshotFile>${project.build.directory}/test-snapshots/social.imps</snapshotFile>
                <consumerSchemas>
                    <consumerSchema>${project.basedir}/contracts/feed-service-v1.imps.schema.yaml</consumerSchema>
                    <consumerSchema>${project.basedir}/contracts/trust-safety-v2.imps.schema.yaml</consumerSchema>
                </consumerSchemas>
            </configuration>
        </execution>
    </executions>
</plugin>
```

If a producer commit removes an attribute, changes a column type, widens nullability from `nullable: false` to `nullable: true`, or drops `CSC` on a relation required by `feed-service-v1.imps.schema.yaml`, `mvn verify` fails before the snapshot is ever published to S3/GCS.

### Ad-Hoc Reverse Schema Extraction

To bootstrap a `schema.yaml` from an existing `.imps` file directly from Maven:

```bash
mvn org.impulsegraph:impulse-maven-plugin:0.11.0:extract-schema \
  -Dimpulse.snapshotFile=datasets/production.imps \
  -Dimpulse.outputFile=src/main/resources/schema.yaml
```

---

## Roadmap: Gradle Plugin & JSR-269 Annotation Processor (`v0.12`)

!!! note "Upcoming in v0.12"
    * **Native Gradle 8/9 Plugin (`org.impulsegraph.impulse`)**: Dedicated incremental Gradle tasks wrapping `CodegenService`, `CompilerService`, and `SchemaService` with Gradle Build Cache support (Gradle users on `v0.11` can invoke `org.impulsegraph.codegen.GeneratorMain` or `org.impulsegraph.cli.ImpulseCliMain` via a standard `JavaExec` task).
    * **JSR-269 `@ImpulseQuery` Annotation Processor**: Compile-time verification of inline Java string queries (`@ImpulseQuery("MATCH (u:User)...")`) directly inside `javac` without external query files.

---

## Next Steps

* **[Pure-Java CLI (`impulse-j`)](cli-impulse-j.md)** — Run the exact same `SchemaService`, `CodegenService`, `SnapshotService`, and `CompilerService` workflows from shell scripts and CI containers.
* **[Day-2 Operations: Kubernetes, Hot-Swap Lifecycle & Schema Evolution](kubernetes-and-lifecycle.md)** — Pair CI `check-compat` gates with runtime `SnapshotLifecycleManager` validation.
