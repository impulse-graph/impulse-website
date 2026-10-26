# Showcase: Anti-Money Laundering (AML) & Fraud Rings

The **Anti-Money Laundering (AML)** showcase demonstrates how Impulse Graph detects deep circular transaction loops ("layering" fraud rings) and enables interactive **"what-if" link analysis** that traditional relational databases struggle to run at scale.

---

## 1. The Real-World Problem

In financial crime and money laundering, illicit funds are rarely sent in a single transfer. Instead, fraudsters split and route funds through a complex web of mule accounts and shell entities—often forming a **circular loop**:

$$\text{Account } A \to B \to C \to D \to \dots \to \text{Account } A$$

In a relational database (`SELECT ... FROM transfers JOIN transfers ...`), every additional hop multiplies the intermediate rows (`multi-set` path explosion). By hop 5 or 6 on a high-volume transaction network, the query runs out of memory or takes minutes.

---

## 2. How Impulse Graph Solves It

Impulse Graph makes deep multi-hop cycle detection and flow aggregation fast enough for interactive investigations:

1. **Set-Based Fixed-Point Reachability (`repeatUntilStable`)**: Instead of generating millions of duplicate path rows, `ImpulseVM` represents the active frontier of reachable accounts as an off-heap **BitSet**. Even if accounts $B$ and $C$ transact back and forth 500 times, converging paths are collapsed into a single bit per account at every step.
2. **Monoidic Flow Reduction (`SUM` / `MIN` / `MAX`)**: When investigators want to track the minimum bottleneck transfer or cumulative flow along a path over the `amount` edge attribute, converging values are reduced in place at each hop.

=== "Java 25 (Circular Fraud Ring Detection)"
    ```java
    // Find all downstream accounts reachable from suspectAccountId across any number of hops
    ImpulseBitSet reachableAccounts = snap.domain("Account")
        .from(suspectAccountId)
        .repeatUntilStable("TRANSFERRED_TO")
        .toBitSet();

    // If the suspect account is in its own downstream reachable set, a circular ring exists
    boolean isPartOfFraudRing = reachableAccounts.get(suspectAccountId);
    ```

---

## 3. What Speed Unlocks: Interactive "What-If" Intermediary Exclusion

Because a full multi-hop closure runs in sub-milliseconds to milliseconds over memory-mapped CSR arrays, compliance analysts can ask interactive **"what-if" counterfactual questions** on the fly—without mutating the graph:

* *"If we freeze or exclude Intermediary Account $B$, does the circular path back to Account $A$ break, or do alternate mule paths still complete the ring?"*
* *"What if we only follow transfers where `edge.amount >= 10000.0`?"*

=== "Java 25 ('What-If' Node Exclusion)"
    ```java
    // Test whether excluding intermediary 'accountB_Id' breaks the circular loop
    boolean cyclePersists = snap.domain("Account")
        .from(suspectAccountId)
        .repeatUntilStable("TRANSFERRED_TO", "node.id != $excludedId")
        .withParam("excludedId", accountB_Id)
        .toBitSet()
        .get(suspectAccountId);

    if (!cyclePersists) {
        System.out.println("Account B is a critical cut-vertex for this fraud ring.");
    }
    ```

Because the `.imps` snapshot is read-only and each query runs in its own pre-allocated workspace, an automated screening job can test **thousands of candidate cut-vertices in parallel** across CPU cores in under a second.
