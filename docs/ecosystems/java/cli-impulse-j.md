# Pure-Java CLI (`impulse-j`) & Tooling Parity

!!! info "Version Note: v0.11 Tooling Suite"
    The pure-Java CLI **`impulse-j`** (`org.impulsegraph:impulse-cli`, shaded classifier `all`) ships in **`v0.11`** (`0.11.0`).

Impulse Graph provides two command-line distributions that operate on the exact same `.imps`, `.imps.schema.yaml`, `.impas`, and `.impb` files:

1. **`impulse-j` (`org.impulsegraph:impulse-cli`)**: A 100% pure-Java CLI packaged as an executable shaded JAR (`impulse-cli-*-all.jar`) with a POSIX `sh` wrapper script.
2. **`impulse-graph` / `impulse` (`impulse-graph-core/impulse-cli`)**: The native Rust/C++20 binary embedding `libimpulse_graph_static.a` (see [Native CLI Reference](../native/cli-reference.md)).

---

## 1. Why `impulse-j` Exists

In many enterprise JVM environments—bank CI runners, air-gapped Artifactory/Nexus networks, locked-down developer laptops, and distroless JRE containers—downloading or approving platform-specific native C++/Rust binaries requires separate security review, whereas fetching a signed JAR from an internal Maven mirror is already standard practice.

`impulse-j` embeds the pure-Java storage loader, streaming CSV/TSV/JSONL snapshot builder, schema validator, AOT code generator, multi-frontend compiler, `QueryExplainer`, and `ImpulseVM` into a single cross-platform artifact that runs anywhere **JDK 21 LTS** or **JDK 22+ / 25 LTS** is installed.

---

## 2. Installation & Invocation

=== "`impulse-j` Launcher Script"

    The `impulse-j` POSIX shell wrapper automatically resolves `JAVA_HOME` (or `java` on `PATH`), locates `impulse-cli-*-all.jar` (or reads `IMPULSE_J_JAR`), inspects `java -version` to inject `--enable-preview` automatically when running on **JDK 21**, and adds `--add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED`:

    ```bash
    # Override JAR path or pass extra JVM heap/GC flags via environment variables:
    export IMPULSE_J_JAR=/opt/impulse/impulse-cli-0.11.0-all.jar
    export IMPULSE_J_OPTS="-Xmx4g"

    impulse-j --version
    impulse-j inspect datasets/social.imps --format json
    ```

=== "Direct `java -jar`"

    Invoke the shaded `-all.jar` directly on JDK 22+ / JDK 25 LTS (add `--enable-preview` before `--add-modules` if running on JDK 21 LTS):

    ```bash
    java --add-modules jdk.incubator.vector \
         --enable-native-access=ALL-UNNAMED \
         -jar impulse-cli-0.11.0-all.jar \
         snapshot validate datasets/social.imps --strict-alignment --deep-audit
    ```

=== "`jbang` (Zero-Install Maven Execution)"

    Run `impulse-j` directly from Maven Central or an internal corporate Maven repository via [JBang](https://www.jbang.dev/):

    ```bash
    jbang --java 25 \
      --runtime-option=--add-modules=jdk.incubator.vector \
      --runtime-option=--enable-native-access=ALL-UNNAMED \
      org.impulsegraph:impulse-cli:0.11.0:all \
      schema extract datasets/social.imps -o schema.yaml
    ```

---

## 3. Command Reference & Exact Flags

```text
impulse-j
├── schema
│   ├── extract       <snapshot> [-o|--output <file>]
│   ├── validate      <schema> [-s|--snapshot <file.imps>] [--format text|json]
│   └── check-compat  -s|--snapshot <file.imps> -c|--consumer <schema.yaml>... [--format text|json]
├── codegen           -s|--schema <schema.yaml|file.imps> -o|--out <dir> [-p|--package <pkg>]
├── snapshot          (build, inspect, stats also available as top-level shorthands)
│   ├── build         -m|--manifest <manifest.yaml|.json> -o|--output <out.imps>
│   ├── inspect       <snapshot> [--format text|json] [--page-map] [--domain <d>] [--relation <r>] [--anonymize]
│   ├── validate      <snapshot> [--strict-alignment] [--quick-check] [--deep-audit] [--format text|json]
│   └── stats         <snapshot> [--format text|json] [-v|--verbose] [--supernode-threshold <z>]
├── compile           <queryFile> [-o|--output <out>] [--schema <yaml>] [-s|--snapshot <imps>] [--emit-ir] [--lang <l>]
├── assemble          -i|--input <in.impas> -o|--output <out.impb>
├── disassemble       -i|--input <in.impb> [-o|--output <out.impas>]
├── explain           <queryFileOrString> [--lang <l>] [-s|--snapshot <imps>] [--schema <yaml>]
└── run               -s|--snapshot <imps> -b|--bytecode <file> [-i|--input-val <id>] [--verify] [--format text|json]
```

### 3.1 Schema Governance (`schema extract | validate | check-compat`)

```bash
# Reconstruct canonical .imps.schema.yaml from any v0.9 / v0.10 .imps binary
impulse-j schema extract production.imps -o extracted.imps.schema.yaml

# Validate YAML structural invariants alone, or verify conformance against a snapshot
impulse-j schema validate src/main/resources/schema.yaml --snapshot production.imps --format json

# Multi-consumer CI compatibility gate (repeatable -c / --consumer flag; exits non-zero on violation)
impulse-j schema check-compat \
  --snapshot candidate-v2.imps \
  --consumer contracts/authz-service.yaml \
  --consumer contracts/fraud-scorer.yaml \
  --format text
```

### 3.2 AOT Java Code Generation (`codegen`)

Accepts either a `.yaml`/`.yml` schema file or a compiled `.imps` binary snapshot:

```bash
impulse-j codegen \
  --schema src/main/resources/schema.yaml \
  --out target/generated-sources/impulse \
  --package com.example.graph.generated
```

### 3.3 Snapshot Lifecycle (`build`, `inspect`, `snapshot validate`, `stats`)

```bash
# Compile CSV, TSV, and JSONL node/edge files from manifest.yaml or manifest.json
impulse-j build -m datasets/manifest.yaml -o datasets/graph.imps

# Inspect Page 0 header, domains, relations, 128B/4KB page map, and SHA-256 in JSON
impulse-j inspect datasets/graph.imps --page-map --format json

# Generate an anonymized inspection bundle (redacts proprietary domain/relation/attribute names)
impulse-j inspect datasets/graph.imps --anonymize --format json > support-bundle.json

# Verify 128B alignment, CSR monotonicity, CSC transpose multiset, and SHA-256 footer
impulse-j snapshot validate datasets/graph.imps --strict-alignment --deep-audit

# Compute degree percentiles (min/avg/P50/P90/P99/max), sparsity, and supernodes (Z-score >= 3.0)
impulse-j stats datasets/graph.imps --verbose --supernode-threshold 3.0 --format json
```

### 3.4 Query Compilation, Disassembly, `explain` & `run`

```bash
# Stage 1 schema-validated lowering to normalized ImpScheme (.impscm) IR (no snapshot required)
impulse-j compile queries/friends.cypher --schema schema.yaml --emit-ir -o target/friends.impscm

# Full Stage 1 + Stage 2 compilation against a snapshot into ImpAsm (.impas) or binary ImpOps (.impb)
impulse-j compile queries/friends.cypher --schema schema.yaml --snapshot graph.imps -o target/friends.impas
impulse-j compile queries/friends.cypher --schema schema.yaml --snapshot graph.imps -o target/friends.impb

# Assemble .impas <-> Disassemble .impb
impulse-j assemble -i target/friends.impas -o target/friends.impb
impulse-j disassemble -i target/friends.impb

# Multi-pass optimizer trace + ImpAsm disassembly report (accepts file path or inline query string)
impulse-j explain "MATCH (u:User)-[:OWNS]->(a:Account) WHERE u._id = 0 RETURN a" \
  --lang cypher --schema schema.yaml --snapshot graph.imps

# Execute .impb, .impas, .impscm, .cypher, .impk, or .implog on ImpulseVM with static register verification
impulse-j run --snapshot graph.imps --bytecode target/friends.impb --input-val 42 --verify --format json
```

---

## 4. Side-by-Side CLI Capability Matrix (`impulse-j` vs. Native `impulse-graph`)

Shared commands between `impulse-j` and the native `impulse-graph` (`impulse`) binary are continuously verified against a **134-check side-by-side parity suite** in `impulse-verification`. Use the table below to choose the right tool for your pipeline:

| Capability / Command | `impulse-j` (Pure Java) | `impulse-graph` (Native Rust/C++20) | Notes |
| :--- | :---: | :---: | :--- |
| **CSV / TSV / JSONL `build`** | Yes | Yes | Byte-for-byte compatible `.imps` output; both mount in Java, Python, C++, and Rust. |
| **Apache Parquet `build`** | — | **Yes** | Native CLI streams Parquet column chunks directly via Arrow/Parquet C++. |
| **Vamana ANN Index Build (`--embeddings`, `--vector-index`)** | — | **Yes** | Built by `impulse build`, `attach-embeddings`, or `optimize`; **queried natively in Java** via `OP_VECTOR_ANN_SEARCH`. |
| **`inspect` (`--format json`, `--page-map`, `--domain`, `--relation`)** | Yes | Yes | 100% parity on structural inspection. |
| **`inspect --anonymize`** | **Yes** | — | Redacts domain, relation, attribute, and metadata identifiers for enterprise support bundles. |
| **`snapshot validate` (`--strict-alignment`, `--quick-check`, `--deep-audit`)** | Yes | Yes | Header CRC, 128B alignment, CSR bounds/monotonicity, CSC transpose multiset, SHA-256. |
| **`stats` (`--supernode-threshold`, `--format json`)** | Yes | Yes | Degree percentiles (`P50`/`P90`/`P99`/`max`) and Z-score supernode counts. |
| **`schema extract \| validate \| check-compat`** | **Yes** | — | Consumer-driven structural subtyping & canonical `.imps.schema.yaml` extraction. |
| **`codegen` (Typed Java Source Emission)** | **Yes** | — | Generates zero-dependency Java 21+ snapshot facades, traversals, CEL metamodels, and `RowView`s. |
| **`compile` / `assemble` / `disassemble` / `run`** | Yes | Yes | Both compile all 4 DSLs, assemble/disassemble `.impas` ↔ `.impb`, and execute `ImpulseVM`. |
| **`explain` (Stage 1 + Stage 2 Pass Trace)** | **Yes** | — | Prints step-by-step AST transformations across `PassTracer` plus final `ImpAsm` disassembly. |
| **`snapshot optimize` (`--rcm`, `--vamana-locality`, `--degree-sort`, `--csc`)** | — | **Yes** | Offline Reverse Cuthill-McKee cache-locality reordering and medoid BFS layout optimization. |
| **`attach-embeddings` / `convert-tensors` / `bench-vector`** | — | **Yes** | `.npy` / `.fvecs` / `.safetensors` ingestion and quantized (`SQ8`/`FP16`/`BQ1`) ANN benchmarking. |
| **`snapshot diff` / `export` / `generate`** | — | **Yes** | Structural snapshot diffing, CSV/TSV/JSONL export, and synthetic Graph500 R-MAT generation. |
| **`crypto` (`keygen`, `sign`, `verify` Ed25519)** | — *(Builder RSA/ECDSA)* | **Yes** | Standalone CLI Ed25519 key generation and detached/footer signature verification. |

---

## Next Steps

* **[Day-2 Operations: Kubernetes, Hot-Swap Lifecycle & Schema Evolution](kubernetes-and-lifecycle.md)** — Automate live snapshot rollouts in production pods.
* **[Native CLI Reference (`impulse-graph`)](../native/cli-reference.md)** — Full documentation for Parquet builds, `--rcm` reordering, and Vamana vector indexing.
