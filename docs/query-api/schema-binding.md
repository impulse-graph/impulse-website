# Schema Binding and Compilation

The query lifecycle explicitly separates AST construction from schema binding and plan compilation.

## The Compile Step

When you call `execute()`, the query must resolve string-based relation names into integer offsets optimized for execution. This process is driven by the `compile()` step.

```text
ImpulseQuery (string-based AST)
       │
       │  execute(view, input) called
       ▼
  Check: is there a CompiledQuery cached for view.schema().fingerprint()?
       │
  NO ──┼──▶  Compile: resolve relation strings → int IDs, validate type chain
       │     Cache result in ImpulseQuery keyed by schema fingerprint
       │
  YES ─┘
       │
       ▼
  CompiledQuery.evaluate(view, input)  ← fast path, no string lookups
```

## Schema Fingerprinting

The system caches the compiled opcode plan keyed by a **schema fingerprint**. The fingerprint is a lightweight hash of the entity types and relations that the query *actually uses*. 

If a new snapshot adds 50 relations your query doesn't care about, the fingerprint stays the same, and no re-compilation occurs.

## String Names as Stable Identity

In the Impulse C-ABI snapshot (`.imps`), relations are identified by an integer ID. However, the **string name** is the stable identity in the codebase.

The compiler resolves the string name to the integer ID present in the *current* `GraphView`. This allows snapshot generators to reorganize IDs across snapshot builds without breaking queries, provided the string names remain stable.
