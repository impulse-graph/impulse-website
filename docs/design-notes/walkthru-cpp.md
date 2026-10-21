# Impulse Graph C++ Engine Integration Walkthrough

This walkthrough guides you through integrating the **Impulse Graph C++** (`impulse-graph-core/impulse-cpp`) engine kernel into an existing C++ application. It covers cloning and building the native C++20 zero-copy kernel, linking static/shared libraries, configuring your build system, opening binary snapshot (`.imps`) files via memory-mapping (`mmap`), executing vector-accelerated graph traversals and neighborhood samplers, and managing dynamic live overlay deltas.

---

## Prerequisites

Before beginning, ensure your environment meets the following requirements:

* **C++20 Compiler**: GCC 11+, Clang 13+, or MSVC 2022+ with standard support (`-std=c++20`).
* **CMake 3.20** or higher.
* **Git** CLI.
* An existing C++ project or build pipeline (CMake, Make, Bazel, etc.).

---

## Step 1: Clone the Repository

Clone the `impulse-graph-core` repository containing the C++20 kernel:

```bash
git clone https://github.com/impulse-graph/impulse-graph-core.git
cd impulse-graph-core/impulse-cpp
```

> [!NOTE]
> If you are working locally within the `~/impulse` multi-repository ecosystem, the C++ engine source is located at `~/impulse/impulse-graph-core/impulse-cpp`.

---

## Step 2: Build and Install C++ Core Engine

`impulse-graph-core/impulse-cpp` builds two primary targets using CMake:
* `impulse_graph_static`: Zero-dependency static library (`libimpulse_graph_static.a` / `impulse_graph_static.lib`).
* `impulse_graph`: Shared dynamic library (`libimpulse_graph.dylib` / `.so` / `.dll`).

Execute the CMake build and install commands:

```bash
# 1. Configure release build
cmake -B build -DCMAKE_BUILD_TYPE=Release

# 2. Compile static and shared libraries
cmake --build build -j$(nproc 2>/dev/null || sysctl -n hw.ncpu)

# 3. Optional: Run verification tests
ctest --test-dir build --output-on-failure

# 4. Optional: Install headers and libraries system-wide (or to a custom prefix)
sudo cmake --install build --prefix /usr/local
```

Upon installation, the following files will be installed:
* Headers: `/usr/local/include/impulse_graph.h`, `/usr/local/include/impulse_sha256.h`
* Libraries: `/usr/local/lib/libimpulse_graph_static.a`, `/usr/local/lib/libimpulse_graph.dylib`
* CMake Package Config: `/usr/local/lib/cmake/ImpulseGraph/ImpulseGraphConfig.cmake`

---

## Step 3: Configure Project Build System

### Option A: CMake Integration (`CMakeLists.txt`)

If your project uses CMake, integrate Impulse Graph using `find_package` or static target linking:

```cmake
cmake_minimum_required(VERSION 3.20)
project(my_rbac_app LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find installed ImpulseGraph CMake package
find_package(ImpulseGraph REQUIRED)

add_executable(rbac_query_app src/main.cpp)

# Link static library (recommended for zero-dependency standalone binaries)
target_link_libraries(rbac_query_app PRIVATE ImpulseGraph::impulse_graph_static)
```

If you prefer to embed `impulse-cpp` directly as a sub-directory in your repository:

```cmake
add_subdirectory(third_party/impulse-graph-core/impulse-cpp)
target_link_libraries(rbac_query_app PRIVATE impulse_graph_static)
```

---

### Option B: Direct Compiler / Makefile Invocation

For manual build configurations or Makefiles, specify the include path and static library explicitly:

```bash
g++ -std=c++20 -O3 -I/usr/local/include src/main.cpp \
    /usr/local/lib/libimpulse_graph_static.a -o rbac_query_app
```

> [!IMPORTANT]
> Impulse Graph C++ relies on C-ABI binary snapshot alignment (128-byte hardware boundary alignment) for AVX-512 SIMD vector acceleration and zero-copy `mmap` performance. Always compile with modern target CPU instructions (`-march=native` or `-mavx2` / `-mavx512f` when targeting modern x86_64 nodes).

---

## Step 4: Open and Read a Binary Snapshot (`.imps`) File

Impulse Graph opens binary snapshot files (`.imps`) direct-to-disk using OS-level zero-copy memory mapping (`mmap`). Physical memory overhead remains $O(1)$ regardless of snapshot file size.

To open and inspect a snapshot file (e.g. `datasets/rbac_snapshot.imps`):

```cpp
#include "impulse_graph.h"
#include <iostream>

impulse_status_t status = IMPULSE_OK;
impulse_snapshot_t* snapshot = impulse_snapshot_open("datasets/rbac_snapshot.imps", &status);

if (status != IMPULSE_OK || !snapshot) {
    std::cerr << "Failed to open snapshot. Error: " << impulse_get_last_error() << std::endl;
    return 1;
}

std::cout << "Snapshot Magic: 0x" << std::hex << impulse_snapshot_magic(snapshot) << std::dec << "\n"
          << "Format Version: " << impulse_snapshot_version(snapshot) << "\n"
          << "Domain Count:   " << impulse_snapshot_domain_count(snapshot) << "\n"
          << "Relation Count: " << impulse_snapshot_relation_count(snapshot) << std::endl;

// Always close snapshot to unmap memory regions
impulse_snapshot_close(snapshot);
```

---

## Step 5: Execute Graph Queries, Reachability & Sampling

The C++ C-ABI kernel provides high-performance lock-free functions to query CSR graph topology and sample node neighborhoods:

### 1. Direct Reachability Lookup (`impulse_snapshot_is_reachable`)

Test whether a directed edge exists between `src_node` and `tgt_node` across a given domain pair:

```cpp
// Check if User 0 has direct edge reachability to Group 5 (src_domain=0, tgt_domain=1)
bool is_connected = impulse_snapshot_is_reachable(snapshot, 0, 0, 1, 5);
if (is_connected) {
    std::cout << "[+] User 0 is directly connected to Group 5" << std::endl;
}
```

### 2. SIMD Neighborhood Sampling (`impulse_snapshot_sample_neighbors`)

Perform zero-copy neighborhood expansion for single-node or batch-node queries (useful for GNN feature extraction, ReBAC expansion, and graph traversals):

```cpp
uint32_t src_nodes[] = { 0 }; // Input seed node IDs
uint32_t out_src[64];
uint32_t out_tgt[64];
size_t out_count = 0;

// Sample up to k=10 neighbors for node 0 on Relation 0 (pass k=-1 for all neighbors)
impulse_status_t st = impulse_snapshot_sample_neighbors(
    snapshot,
    0,            // relation_index
    src_nodes, 1, // input node array and count
    10,           // k_samples (-1 for full expansion)
    42,           // random seed
    out_src, out_tgt, 64, &out_count
);

if (st == IMPULSE_OK) {
    std::cout << "[+] Sampled " << out_count << " neighbors for Node 0:\n";
    for (size_t i = 0; i < out_count; ++i) {
        std::cout << " Edge: " << out_src[i] << " -> " << out_tgt[i] << "\n";
    }
}
```

### 3. Dynamic Live Overlay & Snapshot Compaction

Layer runtime edge additions or tombstones using lock-free dynamic overlay layers (`impulse_delta_layer_t`), and compact them into a new v2.4 binary snapshot:

```cpp
// 1. Create delta layer for relation (src_domain=0, tgt_domain=1)
impulse_delta_layer_t* delta = impulse_delta_layer_create(0, 1, "userToGroup");
impulse_delta_layer_add_edge(delta, 0, 99); // Add new edge 0 -> 99
impulse_delta_layer_tombstone_edge(delta, 0, 5); // Tombstone edge 0 -> 5

// 2. Compact base snapshot + live deltas into a consolidated snapshot on disk
impulse_delta_layer_t* deltas[] = { delta };
impulse_status_t compact_st = impulse_snapshot_compact_to_file(
    snapshot,
    deltas, 1,
    "datasets/compacted_rbac_snapshot.imps"
);

// 3. Clean up delta layer
impulse_delta_layer_destroy(delta);
```

---

## Step 6: Complete End-to-End Executable C++ Example

Below is a self-contained, complete C++ application demonstrating file loading, relation directory inspection, reachability verification, neighborhood sampling, live overlay mutation, and resource cleanup.

```cpp
#include "impulse_graph.h"

#include <iostream>
#include <vector>
#include <filesystem>
#include <iomanip>

int main(int argc, char** argv) {
    std::string snapshot_path = "datasets/rbac_snapshot.imps";
    if (argc > 1) {
        snapshot_path = argv[1];
    }

    std::cout << "=========================================================\n";
    std::cout << " Impulse Graph C++ Engine Query Runner             \n";
    std::cout << "=========================================================\n";

    if (!std::filesystem::exists(snapshot_path)) {
        std::cerr << "[!] Snapshot file not found: " << snapshot_path << "\n";
        std::cerr << " Generating sample snapshot in memory...\n";

        // Build a sample snapshot using impulse_writer_t
        const uint32_t row_offsets[] = { 0, 2, 3, 4 }; // Row offsets for 3 nodes
        const uint32_t col_indices[] = { 1, 2, 2, 0 }; // Edge targets

        impulse_writer_t* writer = impulse_writer_create(snapshot_path.c_str(), 0);
        impulse_writer_add_domain(writer, 0, IMPULSE_KEY_TYPE_INT32, "users");
        impulse_writer_add_domain(writer, 1, IMPULSE_KEY_TYPE_INT32, "roles");
        impulse_writer_add_relation(
            writer, 0, 1,
            IMPULSE_ENC_RAW_UINT32,
            3, 4, 0,
            row_offsets, sizeof(row_offsets),
            col_indices, sizeof(col_indices)
        );
        impulse_writer_finalize(writer);
        impulse_writer_destroy(writer);
        std::cout << "[+] Sample snapshot created at: " << snapshot_path << "\n";
    }

    // 1. Open snapshot file via zero-copy mmap
    impulse_status_t status = IMPULSE_OK;
    impulse_snapshot_t* snapshot = impulse_snapshot_open(snapshot_path.c_str(), &status);

    if (status != IMPULSE_OK || !snapshot) {
        std::cerr << "[!] Failed to open snapshot: " << impulse_get_last_error() << "\n";
        return 1;
    }

    // 2. Inspect Header Metadata
    std::cout << "[+] Snapshot Header Details:\n"
              << "    - Magic:         0x" << std::hex << impulse_snapshot_magic(snapshot) << std::dec << "\n"
              << "    - Version:       " << impulse_snapshot_version(snapshot) << "\n"
              << "    - Domain Count:  " << impulse_snapshot_domain_count(snapshot) << "\n"
              << "    - Rel. Count:    " << impulse_snapshot_relation_count(snapshot) << "\n";

    // 3. Inspect Relation Directory Entries
    uint16_t num_relations = impulse_snapshot_relation_count(snapshot);
    for (uint16_t i = 0; i < num_relations; ++i) {
        impulse_relation_directory_entry_t entry{};
        if (impulse_snapshot_get_relation_entry(snapshot, i, &entry) == IMPULSE_OK) {
            std::cout << "[+] Relation [" << i << "]: "
                      << "SrcDomain=" << entry.src_domain_id << ", "
                      << "TgtDomain=" << entry.tgt_domain_id << ", "
                      << "Nodes=" << entry.node_count << ", "
                      << "Edges=" << entry.edge_count << ", "
                      << "Encoding=" << (int)entry.encoding_type << "\n";
        }
    }

    // 4. Test Reachability Query (User 0 -> Role 1)
    bool reachable = impulse_snapshot_is_reachable(snapshot, 0, 0, 1, 1);
    std::cout << "[+] Edge reachability check (Node 0 -> Node 1): " 
              << (reachable ? "CONNECTED" : "NOT CONNECTED") << "\n";

    // 5. SIMD Neighborhood Sampling
    uint32_t src_nodes[] = { 0 };
    uint32_t out_src[32];
    uint32_t out_tgt[32];
    size_t out_count = 0;

    status = impulse_snapshot_sample_neighbors(
        snapshot, 0, src_nodes, 1, -1, 1337,
        out_src, out_tgt, 32, &out_count
    );

    if (status == IMPULSE_OK) {
        std::cout << "[+] Sampled " << out_count << " neighbors for Node 0:\n";
        for (size_t i = 0; i < out_count; ++i) {
            std::cout << "    - Edge " << i << ": (" << out_src[i] << " -> " << out_tgt[i] << ")\n";
        }
    } else {
        std::cerr << "[!] Neighborhood sampling failed with status code: " << status << "\n";
    }

    // 6. Demonstrate Live Overlay & Tombstone
    impulse_delta_layer_t* delta = impulse_delta_layer_create(0, 1, "userToRole_overlay");
    impulse_delta_layer_add_edge(delta, 0, 999);
    std::cout << "[+] Added live overlay edge: 0 -> 999\n";

    // 7. Cleanup Handles and Unmap Memory
    impulse_delta_layer_destroy(delta);
    impulse_snapshot_close(snapshot);

    std::cout << "[+] Off-heap snapshot memory unmapped and closed cleanly.\n";
    return 0;
}
```

---

## Running the C++ Application

Compile and execute the application with GCC or Clang:

```bash
# 1. Compile main application
g++ -std=c++20 -O3 -I/usr/local/include main.cpp \
    -L/usr/local/lib -limpulse_graph_static -o rbac_query_runner

# 2. Run binary
./rbac_query_runner datasets/rbac_snapshot.imps
```

Expected Output:

```text
=========================================================
       Impulse Graph C++ Engine Query Runner
=========================================================
[+] Snapshot Header Details:
    - Magic:         0x494d5053
    - Version:       2
    - Domain Count:  2
    - Rel. Count:    1
[+] Relation [0]: SrcDomain=0, TgtDomain=1, Nodes=3, Edges=4, Encoding=0
[+] Edge reachability check (Node 0 -> Node 1): CONNECTED
[+] Sampled 2 neighbors for Node 0:
    - Edge 0: (0 -> 1)
    - Edge 1: (0 -> 2)
[+] Added live overlay edge: 0 -> 999
[+] Off-heap snapshot memory unmapped and closed cleanly.
```

---

## Summary Checklist

| Step | Action | Command / Code |
| :--- | :--- | :--- |
| **1. Clone** | Clone engine source | `git clone https://github.com/impulse-graph/impulse-graph-core.git` |
| **2. Build** | Build CMake static & shared libs | `cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build` |
| **3. Install** | Install system-wide | `sudo cmake --install build --prefix /usr/local` |
| **4. Link** | Link target in `CMakeLists.txt` | `target_link_libraries(my_app PRIVATE ImpulseGraph::impulse_graph_static)` |
| **5. Load** | Open `.imps` file via `mmap` | `impulse_snapshot_open("path/to/snapshot.imps", &status)` |
| **6. Query** | Execute reachability / sampling | `impulse_snapshot_is_reachable(...)` / `impulse_snapshot_sample_neighbors(...)` |
| **7. Close** | Unmap and release handles | `impulse_snapshot_close(snapshot)` |
