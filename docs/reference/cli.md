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
├── impulse bench-vector         # Shorthand for `impulse snapshot bench-vector` (Vamana ANN harness)
├── impulse compile              # Shorthand for `impulse compiler compile`
├── impulse inspect              # Shorthand for `impulse snapshot inspect`
├── impulse assemble             # Shorthand for `impulse compiler assemble`
├── impulse disassemble          # Shorthand for `impulse compiler disassemble`
├── impulse generate             # Shorthand for `impulse snapshot generate`
├── impulse stats                # Shorthand for `impulse snapshot stats`
│
├── impulse snapshot             # Binary Snapshot (.imps) Data Lifecycle
│   ├── build                    # Stream-compile Parquet/CSV/TSV manifest (+ embeddings/Vamana) -> .imps
│   ├── attach-embeddings        # Attach external embedding files & Vamana ANN indices to an .imps file
│   ├── bench-vector             # Empirical Vamana ANN indexing & two-stage quantized search benchmark
│   ├── inspect                  # Print header, domain/relation catalog, and section offsets
│   ├── validate                 # Verify 128B alignment, CRC-16, SHA-256, --quick-check, & --deep-audit
│   ├── stats                    # Compute degree distributions, multiplicity, and CBO sketches
│   ├── optimize                 # Offline RCM / Vamana-BFS node reordering, degree sort, and CSC generation
│   ├── diff                     # Compare structural diffs between two .imps snapshots
│   ├── export                   # Export .imps relations to CSV/TSV/JSONL
│   ├── convert-tensors          # Ingest HuggingFace .safetensors weights (+ Vamana ANN) into .imps
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
Compiles CSV, TSV, or Apache Parquet files into a 4KB-page-aligned, 128-byte-section-aligned `.imps` snapshot using a declarative `manifest.json` (see [Building Snapshots (CLI & Python)](../getting-started/snapshot-builder-reference.md)). Optionally attaches external embedding matrices (`--embeddings <SPEC>`) and builds embedded Section 2.6 Vamana ANN indices (`--vector-index <SPEC>`, `IMP_INDEX_VAMANA_ANN = 0x08`, `v0.9.1`):

```bash
# Standard build from manifest.json
impulse snapshot build --manifest manifest.json -o production.imps

# Build with external embeddings and a two-stage SQ8 quantized Vamana ANN index
# --embeddings <SPEC>:   Domain.attr=path[:format=npy|fvecs|bvecs|ivecs|safetensors|parquet|jsonl|csv|tsv][:dim=D][:norm=l2]
# --vector-index <SPEC>: Domain.attr[:R=32][:L=64][:alpha=1.2][:metric=cosine|l2|dot][:quant=sq8|fp16|bq1|none]
impulse build --manifest manifest.json -o production.imps \
  --embeddings "Paper.embedding=embeddings.npy:format=npy:dim=768:norm=l2" \
  --vector-index "Paper.embedding:R=32:L=64:alpha=1.2:metric=cosine:quant=sq8"
```

### `impulse snapshot inspect`, `validate` & `stats`
Inspects domain/relation catalogs, verifies strict spec compliance and checksum integrity, or calculates structural graph statistics:

```bash
# Print human-readable or JSON catalog summary
impulse snapshot inspect production.imps --format json

# Verify 128-byte section alignment, CRC-16 header, and SHA-256 payload digest
impulse snapshot validate production.imps --strict-alignment

# Fast structural header, alignment, and CSR monotonicity check (SQLite PRAGMA quick_check equivalent)
impulse snapshot validate production.imps --quick-check

# Deep O(V + E + N*R) cross-index, CSC transpose multiset, and Vamana ANN graph audit
impulse snapshot validate production.imps --deep-audit

# Compute degree percentiles, multiplicity, and supernodes (Z-score threshold, default 3.0)
impulse snapshot stats production.imps --supernode-threshold 3.0
```

### `impulse snapshot optimize`
Applies offline layout transformations—such as **Reverse Cuthill-McKee (RCM)** bandwidth reduction (`--rcm`), **Vamana Medoid BFS Locality** reordering (`--vamana-locality` for beam-search cache locality), degree sorting (`--degree-sort`), reverse **CSC** generation (`--csc`), or attaching/rebuilding Vamana ANN indices (`--embeddings`, `--vector-index`, `--rebuild-vector-index`):

```bash
# Reorder dense IDs with Reverse Cuthill-McKee (RCM) and generate CSC reverse indices
impulse snapshot optimize -i raw.imps -o optimized.imps --rcm --csc

# Reorder domain nodes by BFS traversal order from the Vamana medoid (or attach/rebuild Vamana index)
impulse snapshot optimize -i raw.imps -o vamana_opt.imps --vamana-locality \
  --embeddings "Paper.embedding=vecs.fvecs:dim=128:norm=l2" \
  --vector-index "Paper.embedding:R=32:L=64:alpha=1.2:metric=cosine:quant=sq8" \
  --rebuild-vector-index
```

### `impulse snapshot diff`, `export`, `convert-tensors`, `attach-embeddings`, `bench-vector` & `generate`
```bash
# Compare domain/edge count deltas between two snapshots
impulse snapshot diff v1.imps v2.imps

# Export snapshot edge lists back to CSV, TSV, or JSONL (--format csv|tsv|jsonl)
impulse snapshot export production.imps --out-dir ./exported_csv/ --format csv

# Ingest HuggingFace .safetensors weights into an .imps snapshot domain (with optional Vamana index)
impulse snapshot convert-tensors -i model.safetensors -o weights.imps --domain ModelWeightNode \
  --vector-index "R=32:L=64:metric=cosine:quant=sq8"

# Attach external embeddings (.npy, .fvecs, .safetensors, .parquet, .jsonl, .csv) & Vamana index to an existing .imps
impulse snapshot attach-embeddings -i base.imps -o with_vecs.imps \
  --embeddings "Doc.embedding=doc_vecs.npy:dim=384:norm=l2" \
  --vector-index "Doc.embedding:R=32:L=64:alpha=1.2:metric=cosine:quant=sq8"

# Run empirical Vamana ANN indexing & two-stage quantized search benchmark (NONE, FP16, SQ8, BQ1)
impulse bench-vector -n 10000 -d 128 -c 24 -q 200 -k 10 \
  --max-degree 24 --ef-construction 64 --alpha 1.2 --metric cosine \
  --ef-search 16,32,64 --compare-optimize --format text
# Or benchmark an existing snapshot / external embedding file:
impulse snapshot bench-vector --snapshot with_vecs.imps --embeddings doc_vecs.npy -q 100 -k 10 --format json

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

# 5. Execute with static bytecode verification, SQLite-style NEVER_CORRUPT assertions,
#    differential optimized-vs-unoptimized checking, and branch coverage telemetry
impulse run --snapshot production.imps --bytecode query.impb \
  --verify --never-corrupt --diff-opt --branch-cov
```

---

## 4. Cryptographic Signing (`impulse crypto`)

```bash
# Generate Ed25519 keypair, sign snapshot, and verify signature before mmap
impulse crypto keygen -o release_key
impulse crypto sign production.imps -k release_key.priv
impulse crypto verify production.imps -k release_key.pub
```
