# Showcase: ReBAC Authorization (Zanzibar)

The **impulse-authz** module demonstrates how Impulse Graph powers sub-microsecond fine-grained authorization, directly inspired by Google's Zanzibar paper.

Relationship-Based Access Control (ReBAC) models permissions as a graph. Checking if a user has access to a document means executing a graph traversal to find a path from the `User` to the `Document` through various `Group`, `Role`, and `Folder` nodes.

## The Challenge

Authorization checks happen on every single API request. They must be incredibly fast (sub-millisecond) and completely consistent with the live state of the system.

## Permission Check Pipelines

Impulse Graph excels at this by compiling permission checks into flat opcode plans executed with zero allocations.

=== "Java"
    ```java
    // Build the permission query once at startup
    ImpulseQuery<Boolean> canEditQuery = ImpulseQuery.builder()
        .input(EntityType.USER, ArgType.SINGLE_NODE)
        // User belongs to Group
        .walkEdge("userToGroup")
        // Group has Role
        .walkEdge("groupToRole")
        // Role grants Permission over Resource
        .walkEdge("roleToPermission")
        // Terminal: Does the resulting set contain our target resource?
        .collect(ReturnType.EXISTS);

    // Execute on the hot path (e.g., inside an interceptor)
    boolean allowed = canEditQuery.execute(ctx, view, requestingUserId);
    ```

## Sub-Microsecond `contains()`

Notice the `ReturnType.EXISTS` terminal. Instead of materializing a full `RoaringBitmap` of all permissions the user has, the engine optimizes the execution plan to return `true` the moment it encounters the target resource ID, pruning unnecessary branches early.

## Live Debezium CDC Sync

To keep the graph completely up-to-date with the source of truth database (e.g., Postgres), `impulse-authz` uses Debezium Change Data Capture (CDC).

1. Postgres mutations (insert `user_group_membership`) are captured by Debezium and placed on a Kafka topic.
2. The `impulse-platform` server consumes these events and immediately applies them to the `CsrDeltaLayer`.
3. Subsequent authorization checks instantly reflect the new membership, fulfilling strict consistency requirements without sacrificing read speed.
