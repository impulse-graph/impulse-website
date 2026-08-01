# Getting Started with Impulse Graph Engine

Welcome to the official documentation for the **Impulse Graph Engine**!

Impulse Graph Engine is an ultra-high-performance, zero-copy, C-ABI binary snapshot graph engine designed for sub-millisecond cold start, sub-microsecond vector traversals, and multi-terabyte (TB+) scale graph analytics.

## Core Value Proposition

In traditional graph databases, loading terabytes of data into memory can take hours, and traversing millions of edges can suffer from garbage collection pauses or pointer-chasing overhead. Impulse Graph Engine flips this paradigm by relying on memory-mapped (`mmap`) binary snapshots directly from NVMe disks. 

Our engine achieves:
- **Sub-millisecond Cold Starts**: Map multi-terabyte graphs into memory instantly without loading times.
- **Zero-Copy Reads**: Execute lock-free graph queries directly over off-heap memory.
- **Hardware Alignment**: AVX-512 vector units and GPU warp coalescing out of the box via 128-byte aligned sections.
- **Polyglot Portability**: Identical core concepts and zero-copy performance across Java 25, C++20, Rust, Python, and .NET.

## Key Features

1. **Static Immutable Snapshots**: Fast, highly optimized binary snapshots (`.imps` files) acting as the ultimate source of truth.
2. **Live Delta Overlay**: A dynamic `CsrDeltaLayer` overlaid on the immutable snapshot, supporting live real-time graph mutations via atomic reference swaps.
3. **Trillion-Node Scale**: 64-bit dense node identifiers with advanced topology compression (SIMD-PFOR, Roaring Bitmaps).
4. **Zero Dependencies**: The core engine libraries maintain strictly zero third-party dependencies.

## Performance Guarantees

* **Latency**: p99 traversals under a microsecond for localized neighborhood hops.
* **Throughput**: Millions of deep multi-hop graph traversals per second per core.
* **Memory**: $O(\text{chunk})$ physical memory footprint during snapshot building, enabling hardware-constrained systems to generate TB+ graphs.

Ready to dive in? Check out the [Installation](installation.md) guide and the [Quickstart](quickstart.md) tutorial!
