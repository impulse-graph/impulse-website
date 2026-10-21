# CLI Reference (`impulse` / `impulse-graph`)

Official CLI documentation for the Impulse Graph Engine developer utilities and compiler suite.

!!! note "Canonical Executable"
    The primary executable name is `impulse-graph`, symlinked as `impulse`.

## Command Naming Directive

* **`compile` ONLY applies to Code**: Compiling DSL scripts (`.impscm`, `.impk`, `.implog`) into `.impas` assembly text or `.impb` bytecode (`impulse compiler compile` / `impulse compile`).
* **`build` ONLY applies to Snapshots**: Building binary `.imps` snapshot files from dataset manifests (`impulse snapshot build` / `impulse build`).

---

## Global Command Structure

```text
impulse-graph CLI

├── impulse run                           <-- Top-level execution entrypoint (runs bytecode or source against .imps)
│
├── impulse compiler                      <-- Compiler & Bytecode Toolchain Subcommands (Code Only)
│   ├── compile                           <-- Compiles DSL scripts (.impscm / .impk / .implog) -> .impas or .impb
│   ├── assemble                          <-- Assembles .impas text -> .impb bytecode
│   ├── disassemble                       <-- Disassembles .impb bytecode -> .impas text
│   └── inspect                           <-- Inspects .impb bytecode headers & opcode stats
│
├── impulse snapshot                      <-- Binary Snapshot (.imps) Data Tooling (Snapshots Only)
│   ├── build                             <-- Builds .imps from Parquet/CSV/TSV manifests
│   ├── merge                             <-- Builds a new snapshot by integrating WAL delta log files
│   ├── inspect                           <-- Inspects .imps headers, catalogs & sections
│   ├── validate                          <-- Validates spec compliance & 128B alignment
│   ├── optimize                          <-- Applies RCM reordering & CSC generation
│   ├── diff                              <-- Compares structural diffs between 2 snapshots
│   ├── export                            <-- Exports .imps snapshot to CSV/TSV/JSONL
│   └── convert-tensors                   <-- Ingests HuggingFace .safetensors weights
│
└── impulse crypto                        <-- Cryptographic Attestation & Signatures
    ├── keygen                            <-- Generates Ed25519 keypairs
    ├── sign                              <-- Signs binary snapshot with private key
    └── verify                            <-- Verifies Ed25519 signature
```

---

## Primary Subcommands

### Top-Level Commands

#### `impulse run`
Execute compiled bytecode query (`.impb`) or script against a binary snapshot (`.imps`).

```bash
impulse run --snapshot production.imps --bytecode reachability.impb --input-val 1042
```

#### `impulse compile` (Code Only)
Shorthand for `impulse compiler compile`. Compiles DSL scripts (`.impscm`, `.impk`, `.implog`) into `.impas` assembly text or `.impb` binary bytecode.

```bash
impulse compile query.impscm -o query.impas
```

#### `impulse build` (Snapshots Only)
Shorthand for `impulse snapshot build`. Builds zero-copy binary snapshot (`.imps`) from dataset manifest.

```bash
impulse build --manifest dataset.json -o graph.imps
```

---

### `impulse compiler` Namespace

#### `impulse compiler compile`
Compile DSL source script (`.impscm`, `.impk`, `.implog`) into `.impas` assembly text or `.impb` bytecode.

```bash
impulse compiler compile reachability.impscm -o reachability.impas
```

| Option | Description |
| :--- | :--- |
| `<INPUT>` | Path to DSL script file (`.impscm`, `.impk`, `.implog`) |
| `-o, --output` | Destination `.impas` or `.impb` file path |
| `--emit-ir` | Emit Intermediate Representation (S-Expressions) to stdout |

#### `impulse compiler assemble`
Assemble textual assembly (`.impas`) into binary bytecode program (`.impb`).

```bash
impulse compiler assemble query.impas -o query.impb
```

#### `impulse compiler disassemble`
Disassemble binary bytecode program (`.impb`) into annotated text assembly (`.impas`).

```bash
impulse compiler disassemble query.impb
```

---

### `impulse snapshot` Namespace

#### `impulse snapshot build`
Build zero-copy binary snapshot (`.imps`) from Parquet/CSV/TSV dataset manifest.

```bash
impulse snapshot build --manifest dataset.json -o production.imps
```

#### `impulse snapshot merge`
Build a new binary snapshot by integrating WAL delta log files (`.impdelta`).

```bash
impulse snapshot merge --base production.imps --deltas wal1.impdelta wal2.impdelta -o updated.imps
```

#### `impulse snapshot inspect`
Inspect binary snapshot header, section directory, domain catalogs, and topology metadata.

```bash
impulse snapshot inspect production.imps --format json
```

#### `impulse snapshot validate`
Validate binary snapshot file against Spec normative requirements and 128-byte hardware alignment.

```bash
impulse snapshot validate production.imps --strict-alignment
```

#### `impulse snapshot optimize`
Apply offline layout optimizations (Reverse Cuthill-McKee graph reordering, degree sort, CSC generation).

```bash
impulse snapshot optimize -i raw.imps -o opt.imps --rcm --csc
```

---

### `impulse crypto` Namespace

#### `impulse crypto keygen`
Generate Ed25519 keypair for snapshot signatures.

```bash
impulse crypto keygen -o impulse_key
```

#### `impulse crypto sign`
Sign binary snapshot file using Ed25519 private key.

```bash
impulse crypto sign production.imps -k impulse_key.priv
```

#### `impulse crypto verify`
Verify Ed25519 cryptographic signature on binary snapshot.

```bash
impulse crypto verify production.imps -k impulse_key.pub
```
