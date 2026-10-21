# Showcase: Anti-Money Laundering (AML)

The **impulse-fintech** module showcases Impulse Graph's capabilities in the financial sector, specifically targeting real-time Anti-Money Laundering (AML) and synthetic fraud ring detection.

## The Challenge

Fraudsters often use complex networks of accounts and micro-transactions to obfuscate the origin of funds. A common pattern is a **circular loop** or **fraud ring**: funds move from Account A → B → C → D and eventually back to Account A. Detecting these deep cycles in real-time as transactions occur is notoriously difficult for traditional relational databases.

## Circular Loop Reachability

Impulse Graph solves this using the `repeatUntilStable` fixed-point iteration operation. It rapidly computes the transitive closure of the transaction graph starting from a suspect account.

=== "Java"
    ```java
    // Query to find all accounts reachable from a given account
    ImpulseQuery<RoaringBitmap> ringDetector = ImpulseQuery.builder()
        .input(EntityType.ACCOUNT, ArgType.SINGLE_NODE)
        // Keep following 'transferredTo' edges until the set stops growing
        .repeatUntilStable(step -> step.walkEdge("transferredTo"))
        .collect(ReturnType.ROARING_BITSET);

    // Execute to get all downstream accounts
    RoaringBitmap downstream = ringDetector.execute(ctx, view, suspectAccountId);

    // If the suspect account is in its own downstream set, we have a cycle!
    boolean isFraudRing = downstream.contains(suspectAccountId);
    ```

## Sub-millisecond Execution

Because the `transferredTo` edges are stored in CPU-cache-friendly, 128-byte aligned CSR arrays, following edges is simply a pointer offset addition. The engine can traverse millions of transactions and compute the stable closure in milliseconds.

## Hypothetical "Freeze Account" Scenarios

Investigators can also run hypothetical queries. "If we freeze Account B, does it break the fraud ring?"

=== "Java"
    ```java
    // Hypothetical delta: remove all outgoing edges from Account B
    ImpulseGraphDelta freezeDelta = ImpulseGraphDelta.builder()
        .removeEdgesFromNode(accountB_Id, "transferredTo")
        .build();

    GraphView hypotheticalView = GraphView.of(baseSnapshot, freezeDelta);
    RoaringBitmap newDownstream = ringDetector.execute(ctx, hypotheticalView, suspectAccountId);

    if (!newDownstream.contains(suspectAccountId)) {
        System.out.println("Freezing Account B breaks the cycle.");
    }
    ```
