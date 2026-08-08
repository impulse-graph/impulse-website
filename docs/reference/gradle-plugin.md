# Gradle Plugin Reference (`impulse-gradle-plugin`)

Welcome to the **Gradle Plugin Reference** for the Impulse Graph Engine.

The `impulse-gradle-plugin` (`io.impulse.graph`) automates schema code generation, CSV-to-binary `.imps` snapshot compilation for testing, and snapshot verification directly from your Gradle builds.

---

## 1. Plugin Registration

Add the Impulse Graph plugin to your Gradle build script:

=== "Gradle Kotlin DSL (`build.gradle.kts`)"

    ```kotlin
    plugins {
        java
        id("io.impulse.graph") version "2.3.0-SNAPSHOT"
    }
    ```

=== "Gradle Groovy DSL (`build.gradle`)"

    ```groovy
    plugins {
        id 'java'
        id 'io.impulse.graph' version '2.3.0-SNAPSHOT'
    }
    ```

---

## 2. Extension Block Configuration (`impulse`)

Configure code generation and testing snapshot properties:

=== "Gradle Kotlin DSL (`build.gradle.kts`)"

    ```kotlin
    impulse {
        schemaFile = file("src/main/resources/schema.yaml")
        outputDirectory = file("build/generated/sources/impulse")
        packageName = "com.example.generated"
        
        // CSV-to-IMPS testing configuration
        csvFile = file("src/test/resources/edges.csv")
        snapshotOutputFile = file("build/snapshots/test.imps")
    }
    ```

=== "Gradle Groovy DSL (`build.gradle`)"

    ```groovy
    impulse {
        schemaFile = file('src/main/resources/schema.yaml')
        outputDirectory = file('build/generated/sources/impulse')
        packageName = 'com.example.generated'
        
        csvFile = file('src/test/resources/edges.csv')
        snapshotOutputFile = file('build/snapshots/test.imps')
    }
    ```

---

## 3. Plugin Tasks

The plugin registers three core tasks in your Gradle build execution graph:

| Task Name | Description | Default Trigger |
| :--- | :--- | :--- |
| **`impulseGenerate`** | Parses `schema.yaml`, generates compile-time type-checked Java/Kotlin query builder classes, and wires output into `sourceSets.main`. | Executed automatically before `compileJava` / `compileKotlin`. |
| **`impulseCompileCsv`** | Compiles CSV edge lists into page-aligned C-ABI Spec v0.9.0 `.imps` binary snapshot files direct-to-disk for testing. | Executed before `test`. |
| **`impulseInspect`** | Inspects a `.imps` binary snapshot file, printing relation names, edge counts, off-heap memory size, and SHA-256 checksums to terminal logs. | Manual or diagnostic pipeline. |

---

## 4. Task Usage Examples

### Generating Query Builders (`impulseGenerate`)

Run code generation on demand:

```bash
./gradlew impulseGenerate
```

Generated query builders are automatically added to Gradle compile classpath:

```java
import com.example.generated.UserQueryBuilder;

ImpulseGraphQuery<RoaringBitmap> query = UserQueryBuilder.from(userId)
    .walkUserToGroup()
    .walkGroupToRole()
    .collectRoaringBitset();
```

---

### Compiling CSV Data to `.imps` Snapshots (`impulseCompileCsv`)

Convert test CSV edge lists into immutable binary snapshots before testing:

```bash
./gradlew impulseCompileCsv
```

Input CSV format (`edges.csv`):
```csv
# src_id, dst_id, relation_name
100, 200, userToGroup
200, 300, groupToRole
100, 300, userToRole
```

---

### Inspecting Snapshot Binaries (`impulseInspect`)

Inspect compiled snapshot binary headers and stats directly from terminal logs:

```bash
./gradlew impulseInspect
```

Sample console output:
```text
=========================================================================
                   IMPULSE GRAPH SNAPSHOT INSPECTOR                      
=========================================================================
 File Path:              /project/build/snapshots/test.imps
 File Size:              20500 bytes
 Off-Heap Footprint:     68 bytes
 Total Relations:        3
 Relation Names:         [groupToRole, userToGroup, userToRole]
 SHA-256 Checksum:       a8f3b2c1...
=========================================================================
```
