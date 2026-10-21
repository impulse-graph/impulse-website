# Query Building Paradigms in Impulse Graph Engine

The **Impulse Graph Engine** supports **three laser-focused query paradigms**, giving developers maximum performance across PyTorch ML pipelines, dynamic runtime UI queries, and Spring Enterprise Java microservices:

1. **Storage-Only Zero-Copy Mode ("Graph Parquet Mode")**: Mounts `.imps` binary snapshots in **0 nanoseconds** (`mmap`) into PyTorch tensors (`snapshot.to_torch_indptr()`, `snapshot.to_torch_indices()`) and NumPy arrays without allocating Java/Python heap RAM.
2. **Dynamic Fluent Builder API** (`ImpulseQueryBuilder` / `QueryBuilder`): Type-safe method-chaining API for runtime, dynamic, or ad-hoc query construction that emits `impOps` bytecode directly with **0 nanoseconds of text parsing overhead**.
3. **Embedded Declarative Annotations (`@ImpLog` / `@ImpK`)**: Embed multi-line Datalog logic rules (`@ImpLog`) or GraphBLAS matrix math (`@ImpK`) directly inside Spring Data Java repository interfaces (similar to `@Query(nativeQuery = true)`), validated at build-time via AOT compilation.

---

## Architecture Overview Matrix

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        3 Core Impulse Graph Execution Paradigms                        │
├───────────────────────────────┬───────────────────────────────┬────────────────────────┤
│ 1. Storage-Only ("Parquet")   │ 2. Dynamic Fluent Builder     │ 3. Embedded @ImpLog / @ImpK│
├───────────────────────────────┼───────────────────────────────┼────────────────────────┤
│ snapshot.to_torch_indptr()    │ QueryBuilder.inputNode()      │ @ImpLog("""            │
│ snapshot.to_torch_indices()   │   .walkEdge("knows")          │ can_read(U, D) :-    │
│                               │   .filterBitset(active)       │ owner(U, D).       │
│                               │   .compile()                  │ """)                   │
├───────────────────────────────┼───────────────────────────────┼────────────────────────┤
│ PyTorch GNNs & NumPy Arrays   │ Dynamic UI & Conditional Ops  │ Spring Boot & ReBAC    │
└───────────────────────────────┴───────────────────────────────┴────────────────────────┘
```

### Pattern 1: Storage-Only Zero-Copy Mode ("Graph Parquet Mode")
```python
import impulse_graph as imp
import torch

# Zero-copy mount .imps snapshot in 0 nanoseconds
snapshot = imp.Snapshot.open("huge_100gb_graph.imps")

# Wrap exact physical C-ABI mmap memory addresses into PyTorch Tensors (0 Bytes copied!)
indptr  = snapshot.to_torch_indptr()   # torch.Tensor
indices = snapshot.to_torch_indices()  # torch.Tensor
```

### Pattern 2: Dynamic Fluent Builder Syntax (Runtime Resolved)
```java
import org.impulsegraph.api.*;

// Multi-hop Relationship-Based Access Control (ReBAC) query: USER -> Group -> Role
ImpulseGraphQuery<BitSet> userRolesQuery = ImpulseGraphQuery.<BitSet>builder()
    .input("USER", ArgType.SINGLE_NODE)
    .walkEdge("userToGroup")
    .walkEdge("groupToRole")
    .collect(ReturnType.ROARING_BITSET);
```

### Pattern 2: Generated Strongly-Typed Builder Syntax
Generate entity query builders from a `GraphSchema` using `SchemaCodeGenerator`:

```java
GraphSchema.EntityDef user = new GraphSchema.EntityDef("User", Map.of("fuelSurcharge", "DOUBLE"));
GraphSchema.EntityDef group = new GraphSchema.EntityDef("Group", Map.of());
GraphSchema.RelationDef userToGroup = new GraphSchema.RelationDef("userToGroup", "User", "Group");

GraphSchema schema = new GraphSchema(List.of(user, group), List.of(userToGroup));
SchemaCodeGenerator generator = new SchemaCodeGenerator("com.example.generated");

// Generates UserQueryBuilder.java, GroupQueryBuilder.java source code files
Map<String, String> generatedClasses = generator.generateClasses(schema);
```

**Using the Generated Typed Builder in Code:**
```java
// Full compile-time type checking and IDE auto-complete!
ImpulseGraphQuery<BitSet> query = UserQueryBuilder.from(seedUserKey)
    .walkUserToGroup()        // Auto-completed by IDE
    .walkGroupToRole()        // Auto-completed by IDE
    .collectRoaringBitset();
```

### Maven Plugin Configuration (`impulse-maven-plugin`)
Automatically generate strongly-typed query builder classes during `mvn generate-sources`:

```xml
<plugin>
    <groupId>io.impulse.graph</groupId>
    <artifactId>impulse-maven-plugin</artifactId>
    <version>2.3.0-SNAPSHOT</version>
    <executions>
        <execution>
            <goals>
                <goal>generate</goal>
            </goals>
            <configuration>
                <schemaFile>${project.basedir}/src/main/resources/schema.yaml</schemaFile>
                <outputDirectory>${project.build.directory}/generated-sources/impulse</outputDirectory>
                <packageName>org.impulsegraph.generated</packageName>
            </configuration>
        </execution>
    </executions>
</plugin>
```

### Gradle Task Configuration (`build.gradle`)
Automatically generate query builder classes during `./gradlew compileJava`:

```groovy
configurations {
    impulseCodegen
}

dependencies {
    impulseCodegen 'io.impulse.graph:impulse-codegen:2.3.0-SNAPSHOT'
}

task generateImpulseSources(type: JavaExec) {
    classpath = configurations.impulseCodegen
    mainClass = 'org.impulsegraph.codegen.GeneratorMain'
    args = [
        "${projectDir}/src/main/resources/schema.yaml",
        "${buildDir}/generated/sources/impulse/java/main",
        'org.impulsegraph.generated'
    ]
}

sourceSets.main.java.srcDir "${buildDir}/generated/sources/impulse/java/main"
compileJava.dependsOn generateImpulseSources
```

---

## 2. Attribute Filtering, Expression Projections & Reducers

The Query API supports node and edge attribute filtering, parallel off-heap array expression projections (`node.fuelSurcharge * edge.miles`), and scalar reducers:

```java
// Project node.fuelSurcharge * edge.miles and compute total scalar cost sum
ImpulseGraphQuery<Double> totalCostQuery = ImpulseGraphQuery.<Double>builder()
    .input("TRUCK", ArgType.SINGLE_NODE)
    .filterNodeAttribute("fuelSurcharge", ">", 5.0)
    .walkEdgeFilteredAttribute("routeToCity", "miles", "<", 500.0)
    .projectExpression("fuelSurcharge", "*", "miles")
    .reduceSum();

// Early termination reducer (short-circuits on first matching value)
ImpulseGraphQuery<Object> firstMatchQuery = ImpulseGraphQuery.<Object>builder()
    .input("TRUCK", ArgType.SINGLE_NODE)
    .walkEdge("routeToCity")
    .projectExpression("fuelSurcharge", "*", "miles")
    .reduceFirst();
```

### Namespaced Extended Operations (`builder.extended()`)
Specialized domain opcodes (such as Powergrid island detection `OP_ISLAND_DETECT`, ReBAC checks `OP_REBAC_CHECK`, motif matching `OP_MOTIF_MATCH_3`) are namespaced under `.extended()`, keeping the core query builder API clean:

```java
ImpulseGraphQuery<BitSet> gridQuery = ImpulseGraphQuery.<BitSet>builder()
    .input("POWERGRID", ArgType.SINGLE_NODE)
    .extended().islandDetect(branch1, branch2)
    .extended().rebacCheck("viewer")
    .collect(ReturnType.ROARING_BITSET);
```

---

## 3. AST Representation & Debugging Tools

Queries export human-readable tree structures and bytecode disassembly for inspection and CLI tooling (`impulse-inspect`).

### Exporting AST Trees (`exportAst`)

```java
String astTree = userRolesQuery.exportAst();
System.out.println(astTree);
```

**Console Output:**
```text
AST Query Pipeline [4 steps]:
├── Step 0: INPUT [argType=SINGLE_NODE]
├── Step 1: WALK_EDGE [relation=userToGroup]
├── Step 2: WALK_EDGE [relation=groupToRole]
├── Step 3: COLLECT [returnType=ROARING_BITSET]
```

### Bytecode Disassembly (`disassemble`)

```java
String disassembly = userRolesQuery.disassemble(graphSnapshot);
System.out.println(disassembly);
```

**Console Output:**
```text
=========================================================================
                  IMPULSE VM BYTECODE DISASSEMBLY
=========================================================================
Instruction Count: 5
Program Memory Segment Size: 40 bytes
-------------------------------------------------------------------------
0x0000: OP_INIT_INPUT_NODE       [flags=0x00, dst=R0 , payload=0x00000000 (0)]
0x0001: OP_CSR_WALK              [flags=0x00, dst=R1 , payload=0x00000000 (0)] -> WALK src=R0 -> dst=R1 via rel[0] ("userToGroup")
0x0002: OP_CSR_WALK              [flags=0x00, dst=R2 , payload=0x00010001 (65537)] -> WALK src=R1 -> dst=R2 via rel[1] ("groupToRole")
0x0003: OP_COLLECT_BITSET        [flags=0x00, dst=R2 , payload=0x00000000 (0)]
0x0004: OP_HALT                  [flags=0x00, dst=R0 , payload=0x00000000 (0)]
=========================================================================
```

---

## 4. Zero-Delay Blue/Green Swaps & Snapshot Unloading

Graph snapshots are frequently swapped at runtime (e.g. blue/green snapshot deployments). Physical relation indices (`0`, `1`, `2`...) can change between snapshot versions.

```
                          Zero-Delay Query Execution Path
                                 (Lock-free read)
                        ┌─────────────────────────────────┐
                        │ AtomicReference<BindingState>   │
                        └────────────────┬────────────────┘
                                         │
                                         ▼
                             QueryBindingState (Immutable)
                         ├── GraphSnapshot snapshot
                         ├── MethodHandle methodHandle
                         └── MemorySegment programSeg
                                         │
                                         ▼
                         ┌────────────────────────────────┐
                         │ Active Query Tracking     │
                         │ snapshot.enterQuery()         │
                         │ try {                      │
                         │ methodHandle.invoke()  │
                         │     } finally {                │
                         │ snapshot.exitQuery()   │
                         │     }                          │
                         └────────────────────────────────┘

                              Blue/Green Swap & Unload Path
                                 (Non-blocking swap)
 [ New Snapshot ] ─────────► Validate & Build New BindingState
                                         │
                                         ▼
                              Atomic Swap: bindingState.set(newState)
                                         │
                                         ▼
 [ Old Snapshot ] ─────────► oldSnapshot.drainAndClose(timeoutMs)
                             (Waits for activeQueryCount == 0, then closes off-heap Arena)
```

### Atomic Re-binding (`rebind`)
`CompiledQuery` stores query state inside an `AtomicReference<QueryBindingState>`. Calling `rebind(newSnapshot)`:
1. Verifies that all logical relations required by the AST exist in `newSnapshot`.
2. Clones the instruction program segment and patches relation payload IDs in-place.
3. Compiles a new JIT `MethodHandle`.
4. Performs an **atomic reference update** (`bindingState.set(newState)`), eliminating lock pauses and latency spikes for concurrent reader threads ("zero delay").

### Active Query Draining & Safe Memory Unloading (`drainAndClose`)
Each `GraphSnapshot` uses a high-throughput `LongAdder activeQueryCount` to track in-flight query executions.

```java
// Swap compiled query binding to new blue/green snapshot
compiledQuery.rebind(newSnapshot);

// Await active queries on old snapshot to drain, then safely unmap off-heap memory
oldSnapshot.drainAndClose(5, TimeUnit.SECONDS);
```
