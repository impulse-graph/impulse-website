# Showcase: PyTorch / GNN Integration

The **impulse-gnn** module bridges the gap between massive-scale graph databases and modern machine learning frameworks. It provides native, zero-copy integration with Python, PyTorch, and PyTorch Geometric (PyG).

## The Challenge

Training Graph Neural Networks (GNNs) on graphs with billions of edges is heavily bottlenecked by data loading and neighborhood sampling. Traditional systems require extracting data from the graph database over a network, parsing it into Python, and then moving it to the GPU.

## Zero-Copy `mmap` Tensor Sampling

Impulse Graph eliminates the network and parsing overhead entirely.

Because the `.imps` snapshot format utilizes 128-byte aligned, uncompressed arrays for dense data structures, PyTorch can map the snapshot file directly into memory as a Tensor (`torch.from_file`).

- **No Serialization**: The data format on disk is exactly the format PyTorch expects in memory.
- **Bypass Python**: The C++ native extension (`torch.ops.impulse.sample_neighbors`) performs sampling directly against the memory-mapped arrays, dropping the results straight into GPU memory using pinned memory or GPUDirect.

## 2-Hop Neighborhood Sampling via `repeat()`

A common operation in GNN training (like GraphSAGE) is sampling an $N$-hop neighborhood around a batch of seed nodes.

=== "Python"
    ```python
    import impulse_graph as ig
    import torch
    
    # Load view (maps file directly)
    view = ig.GraphView.of("/data/social_graph.imps")
    
    # Build a 2-hop neighborhood query
    # repeat(step, count) applies the walk 2 times
    two_hop_query = ig.ImpulseQuery.builder() \
        .input("User", ig.ArgType.BITSET) \
        .repeat(lambda step: step.walk_edge("knows"), 2) \
        .collect(ig.ReturnType.NODE_ARRAY)
        
    # Execute batch sampling
    seed_nodes = torch.tensor([1042, 8911, 4200], dtype=torch.int64)
    
    # Returns a flat tensor of neighbor IDs
    neighbors = two_hop_query.execute(view, seed_nodes)
    ```

## Sub-graph Extraction

The `impulse-gnn` extension can also construct PyG `Data` objects directly by sampling edges and slicing property tensors in C++, providing unparalleled throughput for training pipelines.
