# Workspace build governance

This repository is an integration workspace, not a parent Maven project for
either product. `data-agent/` and `metric-platform/` are independent Git
submodules and own their respective source code, dependency management, and
release lifecycles.

## Build boundaries

| Location | Responsibility | Build command |
| --- | --- | --- |
| Root | Aggregate the checked-out submodules for a local workspace package | `mvn -B -DskipTests package` |
| `data-agent/` | Data Agent backend reactor | `mvn -B -DskipTests package` |
| `metric-platform/` | Metric Platform backend reactor | `mvn -B -DskipTests package` |

The root `pom.xml` is deliberately a pure Maven aggregator. It must not become
the parent POM of either submodule and must not declare a submodule as a child
of the other. This preserves independent builds and prevents relative module
paths from coupling the two repositories.

Frontend dependency installation and builds remain owned by the corresponding
submodule; the Maven aggregate only covers the backend reactors currently
declared by their POM files.

## Change workflow

1. Make product changes in the owning submodule and verify its own build.
2. Commit the submodule change in that repository.
3. Update the root gitlink only when the workspace should pin the new commit.
4. Run `mvn -B -DskipTests package` from the root to validate the combined
   checkout. Run each submodule's full verification separately once its
   formatting and test prerequisites are satisfied.

Use `git submodule update --init --recursive` after cloning or switching to a
root commit whose gitlinks have changed.
