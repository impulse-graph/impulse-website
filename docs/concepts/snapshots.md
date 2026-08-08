# Snapshots

At the heart of the **Impulse Graph Engine** is the **C-ABI Binary Snapshot Specification (v0.9.0)**. Impulse Graph Snapshots (`.imps` files) are immutable, highly optimized binary data files that map directly to physical NVMe disks or stream sequentially to cloud object storage (Amazon S3, Google Cloud Storage).

## Sub-Millisecond Cold Starts

Instead of reading data from disk and deserializing it into complex object heaps (which triggers massive garbage collection pressure and long loading delays), Impulse Graph leverages operating system `mmap` (memory-mapping). 

Mapping a snapshot into memory is an $O(1)$ operation—the OS simply sets up virtual memory pointers to the storage blocks. This guarantees sub-millisecond cold starts regardless of whether your graph is 10 MB or 10 TB.

## Zero-Copy Reads & Hardware Alignment

Impulse Graph Snapshots are structured for immediate vector traversal:
- The graph topology is stored in a highly compressed CSR (Compressed Sparse Row) matrix format.
- Operations access the bytes exactly as they sit in the `mmap` off-heap buffer—zero object allocations and zero memory copying.
- Every major block in the snapshot adheres to **128-byte hardware alignment**. This alignment is critical for triggering AVX-512 SIMD vectorization on modern CPUs and ensuring direct warp coalescing if the snapshot is queried via GPUs (e.g., NVIDIA GPUDirect Storage `cuFile`).

## Single-Pass Cloud S3 Streaming Write

`SnapshotWriter` and `SnapshotBuilder` write binary snapshots in single-pass sequential order direct to cloud object storage (S3/GCS) in $O(\text{chunk})$ physical RAM footprint without requiring random file seeks.

## Section Layout Overview

An `.imps` snapshot is meticulously organized into sequential page-aligned sections:

1. **Section 1: Snapshot Header (Fixed 4KB Page 0)**: The first 64 bytes contain the `IMPS` magic bytes (`0x494D5053`), the version `0x0009`, DataOffset `4096`, and global hardware flags.
2. **Section 2: Catalog, String Table & Directory Table (4KB Page 1)**: The global null-terminated UTF-8 Shared String Table, Domain Catalog array, and sorted Relation Directory Table.
3. **Relation Topology Blocks (128-Byte Aligned)**: Compressed CSR row offsets, target column indices, and optional CSC transpose arrays.
4. **Node & Edge Attribute Blocks (Optional, 128-Byte Aligned)**: Fixed-width SoA attribute arrays (floats, ints, timestamps) and variable-length offset blobs.
5. **Footer & Checksum Block (EOF)**: Multi-map metadata stream, SHA-256 payload checksum, Ed25519 signature block, and 16-byte trailer (`"IMPS"`).

## Multi-Snapshot Queries & Future Research

Future research explores multi-snapshot query execution within `ImpulseVM`, allowing single queries to query across multiple `.imps` snapshots (e.g. Snapshot `A` with `rel0..10` and Snapshot `B` with `rel11..13`):

- **Relation Namespacing (`A::userToGroup`)**: Enables disambiguated cross-snapshot traversals and composite relation handle mapping `(SnapshotID << 16) | RelID`.
- **Zero-Copy & Remapped Node ID Spaces**: Verifies identity mappers at bind-time for $O(1)$ zero-copy pass-through across baseline/delta snapshots, with dense translation vectors (`OP_REMAP_ID_SPACE`) for heterogeneous node ordering.
- **Off-Heap Memory & String Isolation**: Scopes string pool offsets (`VAR_STRING`) and primitive SoA attributes per snapshot base pointer, ensuring safe execution without heap allocations.

