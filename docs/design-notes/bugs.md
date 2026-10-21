# Impulse Graph Ecosystem — Cross-Repository Bug Directory

This root directory index tracks known issues, architectural bugs, and regression test requirements across the Impulse Graph Engine multi-repository ecosystem (`~/impulse/`).

---

## Repository Bug Trackers

1. **`impulse-graph-java`**: impulse-graph-java/bugs.md
   * **BUG-JAVA-001**: `LoadedSnapshot` incomplete interface implementation (`getMetadata` / `getMetadataMap`).
   * **BUG-JAVA-002**: Missing `junit-jupiter-params` dependency breaking `mvn clean install -DskipTests`.
   * **BUG-JAVA-003**: `ImpulseGraphQuery.execute()` returns un-evaluated input stub (`(R) input`).
   * **BUG-JAVA-004**: Relation name key prefixing mismatch (`rel_<idx>_userToGroup` vs `userToGroup`).
   * **BUG-JAVA-005**: Hardcoded `<release>25</release>` with `--enable-preview` breaking non-JDK 25 builds.

2. **`impulse-graph-tooling`**: impulse-graph-tooling/bugs.md
   * **BUG-TOOL-001**: `impulse compile` duplicate domain catalog writing ($N_{relations} \times N_{domains}$).
   * **BUG-TOOL-002**: `impulse inspect` CLI missing `--snapshot` / `-s` flag option.

---

## Testing Policy Requirement
All fixes submitted for bugs listed in these files **MUST** include dedicated regression test cases in the respective repository test suites to ensure zero recurrence.
