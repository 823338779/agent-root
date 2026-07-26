# Codex working documents

This directory is the single workspace location for Codex discussion records, implementation notes, research summaries, review reports, and other cross-repository working documents.

These documents may describe either product, but they do not belong in a product submodule because they record the workspace-level decision process rather than a durable product contract.

Keep the following in the owning submodule instead:

- product README files;
- public API and event contracts;
- operational instructions that apply to a standalone product checkout;
- documentation that must evolve with product code.

Move obsolete diagnostics and generated reports to `tmp/` and do not commit them.
