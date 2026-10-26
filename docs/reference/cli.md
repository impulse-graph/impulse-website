# CLI Reference (`impulse` / `impulse-graph`)

Official reference for the `impulse` (`impulse-graph`) command-line utility and compiler suite (`impulse-graph-tooling`). Every release binary statically embeds `libimpulse_graph_static.a`.

!!! important
    **Command Naming Convention**:

    - **`impulse build`** (`impulse snapshot build`) **ONLY builds `.imps` data snapshots** from CSV/Parquet/TSV manifests.
    - **`impulse compile`** (`impulse compiler compile`) **ONLY compiles query code** (`.impscm`, `.impk`, `.implog`, `.cypher`) into `.impas` assembly or `.impb` bytecode.

---

## 1. Command Hierarchy

```text
impulse-graph (symlinked as `impulse`)
├── impulse run                  # Execute a query or .impb bytecode against an .imps snapshot
├── impulse build                # Shorthand for `impulse snapshot build`
├── impulse compile              # Shorthand for `impulse compiler compile`
├── impulse inspect              # Shorthand for `impulse snapshot inspect`
├── impulse assemble             # Shorthand for `impulse compiler assemble`
├── impulse disassemble          # Shorthand for `impulse compiler disassemble`
├── impulse generate             # Shorthand for `impulse snapshot generate`
├── impulse stats                # Shorthand for `impulse snapshot stats`
│
├── impulse snapshot             # Binary Snapshot (.imps) Data Lifecycle
│   ├── build                    # Stream-compile Parquet/CSV/TSV manifest -> .imps
│   ├── inspect                  # Print header, domain/relation catalog, and section offsets
│   ├── validate                 # Verify 128B alignment, CRC-16 header, and SHA-256 footer
│   ├── stats                    # Compute degree distributions, multiplicity, and CBO sketches
│   ├── optimize                 # Offline RCM node reordering, degree sort, and CSC generation
│   ├── diff                     # Compare structural diffs between two .imps snapshots
│   ├── export                   # Export .imps relations to CSV/TSV/JSONL
│   ├── convert-tensors          # Ingest HuggingFace .safetensors weights into .imps
│   └── generate                 # Synthesize synthetic graphs (graph500, social, grid, etc.)
│
├── impulse compiler             # Query Compiler & Bytecode Toolchain
│   ├── compile (or build)       # Compile DSL (.impscm/.impk/.implog/.cypher) -> .impas or .impb
│   ├── assemble                 # Assemble .impas text -> .impb binary bytecode
│   ├── disassemble              # Disassemble .impb binary bytecode -> annotated .impas
│   └── inspect                  # Inspect .impb instruction counts, registers, and opcodes
│
└── impulse crypto               # Ed25519 Cryptographic Attestation
    ├── keygen                   # Generate Ed25519 keypair (.priv / .pub)
    ├── sign                     # Sign an .imps snapshot footer with Ed25519 private key
    └── verify                   # Verify Ed25519 signature and SHA-256 digest of an .imps file
```

---

## 2. Snapshot Data Commands (`impulse snapshot`)

### `impulse snapshot build` (or `impulse build`)
Compiles CSV, TSV, or Apache Parquet files into a 4KB-page-aligned, 128-byte-section-aligned `.imps` snapshot using a declarative `manifest.json` (see [Building Snapshots (CLI & Python)](../getting-started/snapshot-builder-reference.md)):

```bash
impulse snapshot build --manifest manifest.json -o production.imps
```

### `impulse snapshot inspect`, `validate` & `stats`
Inspects domain/relation catalogs, verifies strict spec compliance and checksum integrity, or calculates structural graph statistics:

```bash
# Print human-readable or JSON catalog summary
impulse snapshot inspect production.imps --format json

# Verify 128-byte section alignment, CRC-16 header, and SHA-256 payload digest
impulse snapshot validate production.imps --strict-alignment

# Compute degree percentiles, multiplicity, and supernodes (Z-score threshold, default 3.0)
impulse snapshot stats production.imps --supernode-threshold 3.0
```

### `impulse snapshot optimize`
Applies offline layout transformations—such as **Reverse Cuthill-McKee (RCM)** bandwidth reduction to cluster connected neighbors into adjacent dense IDs (maximizing L1/L2 cache hits) or adding reverse **CSC** indices:

```bash
impulse snapshot optimize -i raw.imps -o optimized.imps --rcm --csc
```

### `impulse snapshot diff`, `export`, `convert-tensors` & `generate`
```bash
# Compare domain/edge count deltas between two snapshots
impulse snapshot diff v1.imps v2.imps

# Export snapshot edge lists back to CSV, TSV, or JSONL (--format csv|tsv|jsonl)
impulse snapshot export production.imps --out-dir ./exported_csv/ --format csv

# Ingest HuggingFace .safetensors weights into an .imps snapshot domain
impulse snapshot convert-tensors -i model.safetensors -o weights.imps --domain ModelWeightNode

# Generate a synthetic Graph500 (R-MAT) snapshot (scale 14 = 16,384 nodes, edge factor 16)
impulse generate --profile graph500 --scale 14 --edge-factor 16 -o synthetic.imps
```

!!! note
    **Note on `impulse snapshot merge`**: While the CLI taxonomy reserves an `impulse snapshot merge` subcommand stub (`--base <BASE> --deltas <DELTAS>... -o <OUTPUT>`), production updates in Impulse Graph are performed by streaming fresh `.imps` snapshots from updated tables via `impulse build` (or Java `SnapshotBuilder`) and executing an atomic Blue/Green pointer swap (see [Changing Data & Live Updates](../getting-started/handling-mutations.md)).

---

## 3. Query Execution & Compiler Commands (`impulse run` & `impulse compiler`)

```bash
# 1. Compile openCypher, ImpLog, ImpK, or ImpScheme to annotated .impas assembly (or emit IR with --emit-ir)
impulse compile query.impscm -o query.impas

# 2. Assemble .impas text into binary .impb bytecode (-i / --input required)
impulse assemble -i query.impas -o query.impb

# 3. Disassemble or inspect binary .impb bytecode
impulse disassemble -i query.impb
impulse compiler inspect query.impb

# 4. Execute compiled bytecode or assembly against a snapshot
impulse run --snapshot production.imps --bytecode query.impb --input-val 42
```

---

## 4. Cryptographic Signing (`impulse crypto`)

```bash
# Generate Ed25519 keypair, sign snapshot, and verify signature before mmap
impulse crypto keygen -o release_key
impulse crypto sign production.imps -k release_key.priv
impulse crypto verify production.imps -k release_key.pub
```
