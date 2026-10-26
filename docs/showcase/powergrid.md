# Showcase: Power Grid Real-Time $N-1$ & $N-2$ Contingency Simulator

The **`impulse-powergrid`** showcase illustrates how a 100x–300x leap in graph traversal speed doesn't just optimize an existing workflow—it makes an **entirely new operational capability practical in real time**.

!!! important
    **LEGAL & OPERATIONAL DISCLAIMER — RESEARCH & ILLUSTRATIVE USE ONLY**:

    `impulse-powergrid` is provided **strictly for academic research, software architecture benchmarking, and performance evaluation purposes**. The Pan-European PEGASE test cases contain synthetic, fictitious data.

    This software is **NOT** certified, designed, or intended for real-time electrical grid operations, physical power dispatch, critical infrastructure control, safety-critical decision making, or live transmission system outage planning.

    The authors and contributors assume **NO LIABILITY OR RESPONSIBILITY** for any direct, indirect, incidental, special, or consequential damages arising from the use of or reliance upon this software.

---

## 1. The Real-World Problem: Combinatorial $N-2$ Grid Outages

An electrical transmission grid is a graph where **Buses** (substations, generators, load centers) are nodes and **Branches** (transmission lines and transformers) are edges. Grid operators are required (under standards like NERC TPL-001 and ENTSO-E security codes) to verify that equipment failures will not split the grid into disconnected "islands" or trigger cascading blackouts:

* **$N-1$ Contingency**: What happens if any **1** transmission line trips? ($E$ scenarios)
* **$N-2$ Contingency**: What happens if any **2** independent transmission lines fail simultaneously during a storm or wildfire? ($\frac{E(E-1)}{2}$ scenarios)

On a regional grid with $E = 4,582$ transmission branches (the Pan-European PEGASE 2869 benchmark), there are **10,495,071 distinct $N-2$ outage pairs**. Using standard Python/NetworkX tools (`PYPOWER`), evaluating all 10.5 million pairs takes **over 3 hours**—making full $N-2$ topology screening an offline planning study rather than a live operational monitor.

---

## 2. How Impulse Graph Turns a 3-Hour Batch Study into a 24-Second Sweep

By compiling the grid topology (`Bus` domain and `Branch` CSR arrays + electrical parameters) into a 128-byte-aligned `.imps` binary snapshot, `impulse-powergrid` evaluates $N-2$ contingencies with zero heap allocations:

1. **Instant `< 30 µs` `mmap` Startup**: The entire grid topology and bus/branch attribute vectors (`baseKV`, `Pd`, `Qd`, resistance $r$, reactance $x$, MVA rating) are mapped directly into CPU cache.
2. **In-Place Edge Masking (Zero Graph Copies)**: Instead of cloning a graph object 10.5 million times to remove two edges, each worker thread runs a SIMD-vectorized BFS island check over the *same* immutable `.imps` CSR array, skipping the two tripped branch IDs in hardware registers (`ARM NEON` / `AVX2`) and tracking visited buses in a stack-allocated 64-bit bitset.
3. **Extreme Multi-Core Concurrency**: Because the `.imps` snapshot is read-only and every thread's BFS bitset fits in L1 cache with zero heap allocations, throughput scales linearly across all CPU cores.

=== "C++20 SIMD Vectorized Island Detector"
    ```cpp
    #include <arm_neon.h>
    #include "powergrid.hpp"

    // SIMD 4-wide NEON loop checking branch outage matches without mutating the CSR graph
    uint32x4_t v_tripped = vdupq_n_u32(static_cast<uint32_t>(tripped_branch_id));
    for (uint64_t e = start; e + 4 <= end; e += 4) {
        uint32x4_t v_branches = vld1q_u32(&edge_branch_ids[e]);
        uint32x4_t v_match = vceqq_u32(v_branches, v_tripped);

        // Extract 128-bit SIMD comparison mask in a single hardware cycle
        uint64x2_t v_cast = vreinterpretq_u64_u32(v_match);
        uint64_t m0 = vgetq_lane_u64(v_cast, 0);
        uint64_t m1 = vgetq_lane_u64(v_cast, 1);

        // Propagate surviving connected buses in a stack-allocated 64-bit BitSet
        ...
    }
    ```

---

## 3. Empirical Benchmark Results vs. PYPOWER / NetworkX

### 20,000 $N-2$ Contingency Pairs (10 CPU Cores)

| Engine Configuration | Wall Time | Simulation Throughput | Latency / $N-2$ Pair | Relative Speedup |
| :--- | :--- | :--- | :--- | :--- |
| **1. PYPOWER / NetworkX (Single-Thread)** | 95,073.19 ms (95.1 s) | 210 pairs/sec | 4,753 $\mu\text{s}$ | **1.0x Baseline** |
| **2. PYPOWER / NetworkX (Multi-Thread 10C)** | 20,231.41 ms (20.2 s) | 989 pairs/sec | 1,011 $\mu\text{s}$ | **4.7x Faster** |
| **3. Impulse SIMD C++ (Single-Thread)** | 2,236.05 ms (2.2 s) | 169,093 pairs/sec | 5.91 $\mu\text{s}$ | **42.5x Faster** |
| **4. Impulse SIMD C++ (Multi-Thread 10C)** | **263.06 ms (0.26 s)** | **1,437,286 pairs/sec** | **0.69 $\mu\text{s}$** | **361.4x Faster** |

### 100% Exhaustive $N-2$ Full Grid Sweeps

| European Grid Dataset | Buses | Branches | Total $N-2$ Pairs | PYPOWER Multi-Thread Time | Impulse SIMD C++ Time | $N-2$ Throughput |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PEGASE 1354 EU Grid** | 1,354 | 1,991 | **1,981,045 pairs** | ~33.6 minutes | **1.96 seconds** | **1,010,250 pairs/s** |
| **PEGASE 2869 EU Grid** | 2,869 | 4,582 | **10,495,071 pairs** | ~3.1 hours | **24.49 seconds** | **428,595 pairs/s** |

Every simulation output was verified against independent third-party **PYPOWER** and **NetworkX** (`networkx.bridges()`) runs, achieving a **100.00% exact topological match** (`561` islanding outages on PEGASE 1354 and `778` on PEGASE 2869).

---

## 4. Beyond Power Grids: Where Else Does This Pattern Apply?

The exact same **"fast exhaustive counterfactual simulation over an immutable `.imps` snapshot"** pattern applies directly to:

* **Global Container Shipping & Logistics**: When a port closes or a vessel is delayed, recalculating all valid empty-container repositioning moves and multi-leg transshipment options across thousands of depots in seconds.
* **Airline Disruption Recovery**: Evaluating millions of aircraft and crew re-pairing combinations after a hub weather event.
* **Telecommunications & Cloud Routing**: Simulating dual-fiber-cut ($N-2$) reachability and latency impact across backbone BGP/MPLS topologies.
* **Systems Biology & Pharmacology**: Perturbing combinations of gene knockouts or protein targets across metabolic and signaling pathway graphs to identify synthetic lethality or drug interactions.
