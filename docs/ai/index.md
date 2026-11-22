# AI Coding Agents, `SKILL.md` & `llms.txt`

General-purpose LLMs trained primarily on Neo4j, SQL, and NetworkX codebases often hallucinate OLTP mutation queries (`CREATE`, `MERGE`), global node IDs, or slow client-side `for` loops when writing code against **Impulse Graph Engine**.

To give AI coding assistants (Claude Code, Antigravity, Cursor, GitHub Copilot, Windsurf, Gemini, and ChatGPT) exact architectural context, `www.impulsegraph.org` publishes three machine-readable endpoints alongside every documentation build.

---

## 1. Hosted Machine-Readable Endpoints

| Endpoint | Format | Best For | Description |
| :--- | :--- | :--- | :--- |
| **[`/ai/SKILL.md`](/ai/SKILL.md)** | Raw Markdown + YAML Frontmatter | **Claude Code, Antigravity, Cursor, Copilot** | Compact, drop-in Agent Skill & Rules file covering `.imps` immutability, per-domain `0 .. N_d - 1` dense IDs, Kleisli set pipelines, JVM/Python/C-ABI flags, and JSON CLI self-verification. |
| **[`/llms.txt`](/llms.txt)** | Markdown Index ([llmstxt.org](https://llmstxt.org/)) | **Web-Browsing Agents & MCP Fetchers** | Concise architectural mental model plus a structured sitemap of every guide, SDK reference, and specification URL with one-line summaries. |
| **[`/llms-full.txt`](/llms-full.txt)** | Single-File Markdown Corpus | **Claude Projects, Gemini, Cursor `@Docs`, NotebookLM** | Complete concatenation of all navigated Impulse Graph documentation pages, DSL guides, SDK references, and normative `.imps` / `ImpulseVM` specifications in reading order. |

---

## 2. One-Command Agent Setup

Install [`SKILL.md`](/ai/SKILL.md) directly into your repository so coding agents enforce Impulse idioms automatically on every prompt:

=== "Claude Code (`.claude/skills/`)"

    ```bash
    mkdir -p .claude/skills/impulse-graph
    curl -fsSL https://www.impulsegraph.org/ai/SKILL.md \
      -o .claude/skills/impulse-graph/SKILL.md
    ```

    *(Alternatively, append to your root `CLAUDE.md`: `curl -fsSL https://www.impulsegraph.org/ai/SKILL.md >> CLAUDE.md`)*

=== "Antigravity / `.agents/skills`"

    ```bash
    mkdir -p .agents/skills/impulse-graph
    curl -fsSL https://www.impulsegraph.org/ai/SKILL.md \
      -o .agents/skills/impulse-graph/SKILL.md
    ```

=== "Cursor (`.cursor/rules/`)"

    ```bash
    mkdir -p .cursor/rules
    curl -fsSL https://www.impulsegraph.org/ai/SKILL.md \
      -o .cursor/rules/impulse-graph.mdc
    ```

    In Cursor **Settings $\to$ Features $\to$ Docs**, you can also index `https://www.impulsegraph.org/llms-full.txt` under `@ImpulseGraph`.

=== "GitHub Copilot (`.github/copilot-instructions.md`)"

    ```bash
    mkdir -p .github
    curl -fsSL https://www.impulsegraph.org/ai/SKILL.md \
      >> .github/copilot-instructions.md
    ```

---

## 3. Common LLM Hallucinations vs. Correct Impulse Idioms

Without `SKILL.md`, AI assistants frequently apply mutable property-graph or imperative ORM habits that fail at compile time or degrade throughput by $100\times$–$1,000\times$.

### 3.1 Architectural Mental-Model Comparison

| Dimension | Hallucinated Neo4j / Imperative Pattern (Wrong) | Idiomatic Impulse Graph Pattern (Correct) |
| :--- | :--- | :--- |
| **Writes & Updates** | `session.run("MERGE (u:User {id: $id}) SET u.risk = 10")` | Snapshots are immutable read-only `.imps` files; rebuild via `impulse-graph build` / `SnapshotBuilder` and hot-swap via `SnapshotLifecycleManager` / `SnapshotSwapManager`. |
| **Node Identity** | Assumes a single global `nodeId` space across all labels (`User#0 == Account#0` collision). | Every domain owns an independent `0 .. N_d - 1` dense space; anchor queries via `snap.domain("User")` or AOT-generated `bank.users()`, and persist only business keys (`UUID` / `String` / `int64`). |
| **Multi-Hop Traversal** | Nested client-side `for` loops fetching neighbors one node at a time (`N + 1` point lookups). | Single engine-native Kleisli set pipeline (`.out(...).filter(...).toKeyList()`) evaluated in `ImpulseVM` over SIMD bitsets. |
| **Intermediate Hops** | Collects exponential multi-set path lists (`List<Path>`) in heap memory. | Collapses each hop onto a per-domain `BitSet` (or monoid state vector `SUM`/`MIN`/`MAX`), preventing path explosion. |
| **Java Memory & Flags** | Sets `-Xmx64g` for a 50 GB graph and omits FFM / Vector flags. | Sets lean `-Xms2g -Xmx4g` so OS `mmap` page cache holds the `.imps` file; passes `--add-modules jdk.incubator.vector --enable-native-access=ALL-UNNAMED` (plus `--enable-preview` on JDK 21). |
| **PyTorch Workers** | Loads graph into a Python `dict` and forks `DataLoader(num_workers=8)`, duplicating RAM $8\times$ via CoW. | Passes only the `.imps` path string to workers and opens `Snapshot(path)` lazily per worker (`0 bytes` duplicated). |

### 3.2 Side-by-Side Code Comparison

=== "Java 21/25"

    ```java
    // ❌ ANTI-PATTERN (Hallucinated Imperative N+1 Point-Lookup Loop):
    // Crosses API boundary per node, allocates heap HashSets per hop, and mixes raw dense IDs!
    Set<String> suspiciousAccounts = new HashSet<>();
    for (long ownedAcc : snap.domain("User").fromKey(userUuid.toString()).out("OWNS").toList()) {
        for (long targetAcc : snap.domain("Account").from(ownedAcc).out("TRANSFERRED_TO").toList()) {
            suspiciousAccounts.add(snap.domain("Account").toKey(targetAcc));
        }
    }

    // ✅ IDIOMATIC IMPULSE PATTERN (Single Zero-Allocation Kleisli Set Pipeline):
    // Executes entirely off-heap inside ImpulseVM via CSR bitset walks + SIMD CEL filtering:
    List<String> suspiciousAccounts = snap.domain("User")
        .fromKey(userUuid.toString())
        .out("OWNS")
        .out("TRANSFERRED_TO", "edge.amount >= 10000.0")
        .filter("node.balance >= 50000.0")
        .toKeyList();
    ```

=== "Python (`impulse-graph`)"

    ```python
    # ❌ ANTI-PATTERN (Client-Side Python Loop Over Adjacency Lists):
    # Re-enters pybind11 per node and materializes intermediate Python lists!
    reached = set()
    for acc_id in snap.traverse(start_node=0).out("OWNS").to_list():
        for dst_id in snap.traverse(start_node=acc_id).out("TRANSFERRED_TO").to_list():
            reached.add(dst_id)

    # ✅ IDIOMATIC IMPULSE PATTERN (Domain-Anchored Engine Pipeline):
    # Resolves business key in User domain, walks both CSR relations in C++20 ImpulseVM,
    # and resolves surviving Account dense IDs back to business keys:
    with Snapshot("banking.imps") as snap:
        reached_keys = (
            snap.domain("User")
                .from_key("usr_101")
                .out("OWNS")
                .out("TRANSFERRED_TO")
                .filter("account.balance >= 1000.0")
                .to_key_list()
        )
    ```

---

## Next Steps

* **[Download Raw `SKILL.md`](/ai/SKILL.md)** — Drop directly into `.claude/skills/`, `.agents/skills/`, or `.cursor/rules/`.
* **[Core Concepts & Glossary](../getting-started/core-concepts.md)** — Visual primer on `.imps` snapshots, per-domain dense IDs, and Kleisli frontier propagation.
* **[Java & JVM Enterprise Hub](../ecosystems/java/index.md)** · **[Python, Data Science & ML Hub](../ecosystems/python/index.md)** · **[Native Systems & C-ABI Hub](../ecosystems/native/index.md)** — Ecosystem-specific guides.
