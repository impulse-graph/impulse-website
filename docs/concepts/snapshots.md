# Snapshots

At the heart of the Impulse Graph Engine is the **C-ABI Binary Snapshot Specification (v2.3)**. Snapshots (`.imps` files) are immutable, highly optimized data files that map directly to physical NVMe disks.

## Sub-Millisecond Cold Starts

Instead of reading data from disk and deserializing it into complex object heaps (which triggers massive garbage collection pressure and hours of loading time), Impulse Graph leverages operating system `mmap` (memory-mapping). 

Mapping a snapshot into memory is an $O(1)$ operation—the OS simply sets up virtual memory pointers to the disk blocks. This guarantees sub-millisecond cold starts regardless of whether your graph is 10 MB or 10 TB.

## Zero-Copy Reads & Alignment

Snapshots are structured for immediate traversal:
- The graph topology is stored in a highly compressed CSR (Compressed Sparse Row) format.
- Operations access the bytes exactly as they sit in the `mmap` buffer—zero object allocations and zero memory copying.
- Every major block in the snapshot adheres to **128-byte alignment**. This alignment is critical for triggering AVX-512 SIMD vectorization on modern CPUs and ensuring direct warp coalescing if the snapshot is queried via GPUs (e.g., NVIDIA GPUDirect Storage).

## Section Layout Overview

An `.imps` snapshot is meticulously organized into sequential sections:

1. **Magic & Header Flags**: The first 64 bytes contain the `IMPS` magic bytes (`0x494D5053`), the version `0x0002`, and global hardware flags.
2. **Relation Directory & Domain Catalog**: Metadata mapping string schemas into internal integers.
3. **Compressed CSR Topology**: The raw vector lists containing edge offsets and target nodes.
4. **ID Mappings (Optional)**: B-Tree mappings converting external strings or UUIDs to internal 64-bit `NodeIndex` values.
5. **DTO Property Payloads (Optional)**: Columnar property arrays for fast attribute retrieval.
6. **Delta Log (Optional)**: A write-ahead log appending late-stage mutations.

## Static Immutable Semantics

Once compiled by the `SnapshotBuilder` or `impulse-opt`, a snapshot never changes. Immutability guarantees absolute thread-safety, allowing tens of thousands of concurrent threads to read the same memory-mapped topology without a single lock or mutex. Mutations are handled externally via the [Delta Overlay](delta-overlay.md).
