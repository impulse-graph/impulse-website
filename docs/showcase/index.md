# Showcase Applications: One Engine, Every Domain

The showcase applications in the Impulse Graph ecosystem exist for two reasons:

1. **To show how the exact same graph primitives apply across wildly different industries**: Whether your nodes are users and documents, bank accounts, electrical substations, shipping containers, or genes and proteins, underneath they all compile down to the same **domain-to-domain frontier steps, SIMD attribute filters, and monoidic reductions** over `.imps` snapshots.
2. **To show how extreme traversal speed makes *entirely new analyses* practical**: When a multi-hop graph query drops from tens of milliseconds to **microseconds**, you don't just make an existing dashboard faster—you can run **millions of "what-if" simulations in real time** that previously had to be overnight batch jobs (or couldn't be computed at all).

---

## Triggering Your Imagination: How Different Domains Map to Impulse Graph

| Industry & Domain | Nodes (Domains) & Edges (Relations) | Core Graph Operation | What Impulse Graph's Speed Makes Practical |
| :--- | :--- | :--- | :--- |
| **[Security & ReBAC (Zanzibar)](authz.md)** | `User` $\to$ `Group` $\to$ `Role` $\to$ `Resource` | Fixed-point reachability & early-exit `contains()` | Checking deep, transitive group/folder permissions in-process on **every single API request** (`< 1 µs`) with zero external network hops. |
| **[FinTech & Anti-Money Laundering](aml.md)** | `Account` $\xrightarrow{\text{TRANSFERRED\_TO}}$ `Account` | Fixed-point cycle detection (`repeatUntilStable`) & `SUM`/`MIN` reductions | Detecting multi-hop circular money-laundering rings and running interactive **"what-if" node-exclusion scenarios** in milliseconds. |
| **[Electrical Power Grids](powergrid.md)** | `Substation Bus` $\xrightarrow{\text{BRANCH}}$ `Substation Bus` | Exhaustive $N-1$ & $N-2$ edge-removal island detection | Simulating **all 10.5 million $N-2$ dual-line outage combinations** across a continental grid in **24 seconds** instead of **3+ hours**. |
| **Logistics, Shipping & Aviation** *(Upcoming Showcase)* | `Container` $\to$ `Depot/Port` $\xrightarrow{\text{LEG}}$ `Port` | Constrained multi-hop reachability & `MIN` cost reduction | **Recalculating all empty-container repositioning move options** across a shipping fleet (or airline crew/aircraft recovery routes) in real time when a port or hub is disrupted. |
| **Pharma, Genomics & Drug Discovery** | `Compound` $\to$ `Protein` $\to$ `Pathway` $\to$ `Gene` $\to$ `Disease` | Multi-domain Kleisli walks & path-weight reduction | Screening millions of multi-hop **drug-pathway-gene interactions** and off-target toxicity cascades interactively over biomedical knowledge graphs (Hetionet, DRKG). |
| **[AI & Graph Neural Networks](gnn.md)** | `Node` $\to$ `Neighbor` / `Token` $\to$ `Expert` | Zero-copy `.imps -> PyTorch` `mmap` tensors & C-ABI neighborhood sampling | Training and sampling over **graphs way larger than physical RAM** with `< 1 ms` cold start and `0 bytes` of `DataLoader` worker duplication (impossible with `Parquet -> PyTorch`). |

---

## Explore the Showcases

* **[Authorization (ReBAC / Zanzibar)](authz.md)**: Sub-microsecond in-process permission checks paired with periodic `.imps` Blue/Green snapshot rotation.
* **[Anti-Money Laundering (AML) & Fraud Rings](aml.md)**: Transitive cycle detection and interactive "what-if" intermediary exclusion using `repeatUntilStable`.
* **[Power Grid Stability ($N-1$ & $N-2$ Contingency Simulator)](powergrid.md)**: How zero-copy `.imps` snapshots and SIMD bitsets turn a 3-hour continental grid outage sweep into a 24-second real-time check.
* **[Graph Neural Networks & PyTorch (`impulse-gnn`)](gnn.md)**: If you live in PyTorch, you'll be right at home—zero-copy `mmap` tensor views, zero `DataLoader` RAM duplication, and high-speed GPU/CPU sparse matrix operations.
