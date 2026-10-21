# Node.js, Bun & TypeScript SDK Reference (`impulse-node`)

This reference documents the **Impulse Graph Engine Node.js / Bun / TypeScript SDK** (`impulse-graph`, located in `impulse-graph-core/impulse-node`).

Built on N-API (`node-addon-api`) with zero external npm runtime dependencies and complete TypeScript declarations (`index.d.ts`), `impulse-node` exposes zero-copy `mmap` snapshot reading, typed-array CSR writing, fluent traversals, and native `ImpulseVM` bytecode execution.

---

## 1. Installation

```bash
npm install impulse-graph
```

---

## 2. Snapshot & Fluent Traversal API

```typescript
import { Snapshot } from 'impulse-graph';

const snap = new Snapshot('social_graph.imps');

// Direct edge reachability check
const exists: boolean = snap.isReachable(0, 0, 0, 1);

// Multi-hop fluent traversal
const friendsOfFriends = snap
  .traverse(0)
  .out(0)
  .out(0)
  .toArray();

console.log('Reachable users:', friendsOfFriends);
snap.close();
```

---

## 3. Streaming Snapshot Writer (`Writer`)

Accepts standard JavaScript `Uint32Array` and `Buffer` views for zero-copy C-ABI ingestion:

```typescript
import { Writer } from 'impulse-graph';

const writer = new Writer('graph.imps');
writer.addDomain(0, 4 /* KeyType INT64 */, 'User');

const rowOffsets = new Uint32Array([0, 2, 4, 5, 5]);
const colIndices = new Uint32Array([1, 2, 2, 3, 3]);

writer.addRelation(
  0, // srcDomainId
  0, // tgtDomainId
  0, // encodingType (RAW_UINT32)
  4, // nodeCount
  5, // edgeCount
  0, // sectionFeatures
  rowOffsets,
  colIndices
);

writer.finalize();
```

---

## 4. Native Bytecode VM API (`QueryBuilder`, `CompiledQuery`, `VmContext`)

```typescript
import { Snapshot, QueryBuilder, VmContext, VmState } from 'impulse-graph';

const snap = new Snapshot('rbac.imps');
const ctx = new VmContext(snap);
const state = new VmState();

const compiled = new QueryBuilder()
  .inputNode(0)
  .walkEdge(0)
  .repeatUntilStable((q) => {
    q.walkEdge(1);
  })
  .collectBitset()
  .compile();

const result = compiled.executeWithContext(ctx, state, 42n);
if (result.isOk()) {
  const allowed = result.testBitset(ctx, 7n);
  console.log('Permission granted:', allowed);
}

ctx.destroy();
snap.close();
```

### Exported Classes (`index.d.ts`)

| Class | Key Methods |
| :--- | :--- |
| **`Snapshot`** | `new Snapshot(path)`, `isReachable(srcDomain, srcId, tgtDomain, tgtId)`, `traverse(seed)`, `close()` |
| **`Writer`** | `new Writer(outputPath, globalFeatures?)`, `addDomain(domainId, keyType, name)`, `addRelation(...)`, `finalize()` |
| **`QueryBuilder`** | `inputNode()`, `inputSet()`, `walkEdge()`, `walkCsc()`, `filterNode()`, `unionWith()`, `intersectWith()`, `differenceWith()`, `cardinality()`, `matrixVectorMul()`, `afforest()`, `sampleNeighbors()`, `rebacCheck()`, `repeat()`, `repeatUntilStable()`, `collectBitset()`, `collectArray()`, `compile()` |
| **`CompiledQuery`** | `execute(snapshot, inputParam?)`, `executeWithContext(ctx, state, inputParam?)`, `instructionCount()`, `resultRegister()`, `bytecode()` |
| **`QueryResult`** | `isOk()`, `asInt()`, `asFloat()`, `asDouble()`, `testBitset(ctx, nodeId)`, `status`, `resultRegister`, `resultType`, `rawValue` |
| **`VmContext`** | `acquireBitset()`, `bitsetAdd()`, `bitsetTest()`, `acquireFloatVector()`, `getFloatVector()` (`Float32Array`), `acquireDoubleVector()`, `getDoubleVector()` (`Float64Array`), `acquireNodeVector()`, `getNodeVector()` (`BigUint64Array`), `destroy()` |
| **`VmState`** | `getRegister(reg)`, `setRegister(reg, val)`, `getRegisterType(reg)`, `getPc()`, `getFlags()` |
