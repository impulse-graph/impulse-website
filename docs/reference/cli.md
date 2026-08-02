# CLI Reference (`impulse` / `impulse-graph`)

Auto-generated CLI documentation for the Impulse Graph Engine developer tooling suite.

!!! note "Canonical Executable"
    The primary executable name is `impulse-graph`, symlinked as `impulse`.

## Global Usage
```bash
impulse <COMMAND> [OPTIONS]
```

## Subcommands

### `impulse inspect`
Inspect binary snapshot header, section directory, domain catalogs, and topology metadata

**Usage:**
```bash
impulse inspect [OPTIONS]
```

**Arguments:**

| Argument | Description |
| :--- | :--- |
| `<file>` | Path to binary snapshot file (.imps) |

**Flags & Options:**

| Flag / Option | Description | Default |
| :--- | :--- | :--- |
| `-f`, `--format` | Output format (text, json) | text |
| `-v`, `--verbose` | Verbose detail dumping (including offset tables and encoding feature bitmaps) |  |

---
### `impulse validate`
Validate binary snapshot file against Spec v2.4 normative requirements

**Usage:**
```bash
impulse validate [OPTIONS]
```

**Arguments:**

| Argument | Description |
| :--- | :--- |
| `<file>` | Path to binary snapshot file (.imps) |

**Flags & Options:**

| Flag / Option | Description | Default |
| :--- | :--- | :--- |
| `--strict-alignment` | Verify 128-byte hardware alignment rules strictly | true |
| `-p`, `--public-key` | Optional public key file to verify Ed25519 signature |  |

---
### `impulse compile`
Compile edge list CSV/TSV/JSON-L data into zero-copy binary snapshot (.imps)

**Usage:**
```bash
impulse compile [OPTIONS]
```

**Flags & Options:**

| Flag / Option | Description | Default |
| :--- | :--- | :--- |
| `-m`, `--manifest` | Path to JSON compiler manifest file |  |
| `-o`, `--output` | Output binary snapshot destination path (.imps) |  |

---
### `impulse optimize`
Heavy offline snapshot layout optimizer (RCM graph reordering, vector encodings, section stripping)

**Usage:**
```bash
impulse optimize [OPTIONS]
```

**Flags & Options:**

| Flag / Option | Description | Default |
| :--- | :--- | :--- |
| `-i`, `--input` | Input binary snapshot (.imps) |  |
| `-o`, `--output` | Output optimized snapshot destination (.imps) |  |
| `--rcm` | Apply Reverse Cuthill-McKee (RCM) bandwidth reduction and cache-line reordering |  |
| `--encoding` | Target CSR column encoding (raw_uint32, delta_vbyte, simdcomp, sliced_ellpack) |  |
| `--strip-mappings` | Strip string ID mapping catalog for minimal runtime binary footprint |  |
| `--strip-properties` | Strip DTO property payload blocks |  |

---
### `impulse keygen`
Generate Ed25519 keypairs for snapshot signature verification

**Usage:**
```bash
impulse keygen [OPTIONS]
```

**Flags & Options:**

| Flag / Option | Description | Default |
| :--- | :--- | :--- |
| `-o`, `--out` | Destination directory or file path prefix for generated keypair | impulse_key |

---
### `impulse sign`
Sign a binary snapshot using Ed25519 private key

**Usage:**
```bash
impulse sign [OPTIONS]
```

**Arguments:**

| Argument | Description |
| :--- | :--- |
| `<file>` | Target binary snapshot file (.imps) |

**Flags & Options:**

| Flag / Option | Description | Default |
| :--- | :--- | :--- |
| `-k`, `--key` | Path to Ed25519 private key file (hex/pem) |  |

---
### `impulse verify`
Verify Ed25519 signature on a binary snapshot

**Usage:**
```bash
impulse verify [OPTIONS]
```

**Arguments:**

| Argument | Description |
| :--- | :--- |
| `<file>` | Target binary snapshot file (.imps) |

**Flags & Options:**

| Flag / Option | Description | Default |
| :--- | :--- | :--- |
| `-k`, `--key` | Path to Ed25519 public key file (hex/pem) |  |

---
### `impulse diff`
Compare structural topology and schema differences between two binary snapshots

**Usage:**
```bash
impulse diff [OPTIONS]
```

**Arguments:**

| Argument | Description |
| :--- | :--- |
| `<base>` | Base binary snapshot file (.imps) |
| `<target>` | Target binary snapshot file (.imps) |

---
### `impulse export`
Export binary snapshot file (.imps) back to CSV/TSV edge lists

**Usage:**
```bash
impulse export [OPTIONS]
```

**Arguments:**

| Argument | Description |
| :--- | :--- |
| `<file>` | Input binary snapshot file (.imps) |

**Flags & Options:**

| Flag / Option | Description | Default |
| :--- | :--- | :--- |
| `-o`, `--out-dir` | Output directory for exported edge files |  |
| `-f`, `--format` | Export format (tsv, csv, jsonl) | tsv |

---
