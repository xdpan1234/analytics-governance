# Analytics Schema

This directory is the machine-readable contract for shared Android and iOS analytics events.

Use one YAML file per product area or event family. Each file should capture event names, platform trigger boundaries, required and optional properties, allowed enum values, privacy notes, dashboard usage, and verification steps.

Agents and developers should update schema before implementing production instrumentation. POC-only events can stay in `docs/provider-poc-playbook.md` unless they graduate into the formal Tracking Plan.
