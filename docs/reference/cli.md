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
│
├── impulse snapshot             # Binary Snapshot (.imps) Data Lifecycle
│   ├── build                    # Stream-compile Parquet/CSV/TSV manifest -> .imps
│   ├── inspect                  # Print header, domain/relation catalog, and section offsets
│   ├── validate                 # Verify 128B alignment, CRC-16 header, and SHA-256 footer
│   ├── optimize                 # Offline RCM node reordering, degree sort, and CSC generation
│   ├── merge                    # Merge base .imps with delta log files (.impdelta)
│   ├── diff                     # Compare structural diffs between two .imps snapshots
│   └── export                   # Export .imps domains/relations to Parquet/CSV/JSONL
│
├── impulse compiler             # Query Compiler & Bytecode Toolchain
│   ├── compile                  # Compile DSL (.impscm/.impk/.implog/.cypher) -> .impas or .impb
│   ├── assemble                 # Assemble .impas text -> .impb binary bytecode
│   ├── disassemble              # Disassemble .impb binary bytecode -> annotated .impas
│   └── inspect                  # Inspect .impb instruction counts, registers, and scratch size
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

### `impulse snapshot inspect` & `validate`
Inspects domain/relation catalogs or verifies strict spec compliance and checksum integrity:

```bash
# Print human-readable or JSON catalog summary
impulse snapshot inspect production.imps --format json

# Verify 128-byte section alignment, CRC-16 header, and SHA-256 payload digest
impulse snapshot validate production.imps --strict-alignment
```

### `impulse snapshot optimize`
Applies offline layout transformations—such as **Reverse Cuthill-McKee (RCM)** bandwidth reduction to cluster connected neighbors into adjacent dense IDs (maximizing L1/L2 cache hits) or adding reverse **CSC** indices:

```bash
impulse snapshot optimize -i raw.imps -o optimized.imps --rcm --csc
```

### `impulse snapshot merge`, `diff` & `export`
```bash
# Integrate delta logs into a fresh immutable snapshot
impulse snapshot merge --base production.imps --deltas batch1.impdelta -o next.imps

# Compare domain/edge count deltas between two snapshots
impulse snapshot diff v1.imps v2.imps

# Export snapshot back to Parquet or CSV
impulse snapshot export production.imps --output-dir ./exported_csv/
```

---

## 3. Query Execution & Compiler Commands (`impulse run` & `impulse compiler`)

```bash
# 1. Compile openCypher, ImpLog, ImpK, or ImpScheme to annotated .impas assembly
impulse compile query.impscm --snapshot production.imps -o query.impas

# 2. Assemble .impas text into binary .impb bytecode
impulse compiler assemble query.impas -o query.impb

# 3. Execute compiled bytecode or source script against a snapshot
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
