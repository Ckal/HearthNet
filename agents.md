# HearthNet Agent Coordination

## Active Roles

| Agent | Role | Ownership |
| --- | --- | --- |
| Codex lead | Integration, docs, final verification, deployment | Whole repo coordination |
| Planck | Phase 1 doc synthesis | Read-only docs review |
| Avicenna | Prototype assessment | Read-only HTML/README review |
| Kepler | HF Space and quality checklist | Read-only deployment/tooling review |
| Mill | Python Phase 1 core | `hearthnet/`, `tests/` |
| Anscombe | Gradio Space UI | `app.py`, optional `static/` |
| Hypatia | Quality/tool config | `pyproject.toml`, requirements, config files |
| Darwin | M01-M07 + contract/glossary audit | Read-only coverage review |
| Gibbs | M08-M13 audit | Read-only coverage review |
| Franklin | X01-X04 + overview/PRD audit | Read-only coverage review |
| Mendel | No-mock local-first model architecture audit | Read-only implementation review |
| Pascal | Gradio/server/UI audit | Read-only UI/runtime review |
| Erdos | Coordination docs policy audit | Read-only tasks/agents review |

## Collaboration Rules

- Workers have disjoint write scopes.
- No worker may revert another worker's edits.
- Services do not import each other directly; they communicate through the bus.
- UI talks to the controller/facades, not directly to services.
- No mocks or fake AI paths in implementation-facing code. Phase 1 may keep clearly labeled prototype/demo surfaces, but shipped services must use real local-first components or explicit unavailable/degraded states.
- Local AI must be local-first: prefer Ollama, llama.cpp, or local Hugging Face Transformers backends. OpenAI may be used only as an opt-in online fallback when local models are unavailable or explicitly disabled.
- Do not add security-tool suppression pragmas, broad ignores, or Bandit/Ruff/Pylint bypasses to pass checks. Fix the finding or document a narrow, reviewed exception in `tasks.md`.
- Quality gates must be run before deployment.
- UI must follow the spec architecture: UI talks through controller/facades/bus snapshots only, with no direct service imports.
- Spec adherence is a quality gate: changes must map to the relevant M/X docs, capability contract, and glossary terms.

## Integration Checklist

- [ ] Merge worker changes.
- [ ] Resolve conflicts without losing existing prototypes.
- [ ] Update `tasks.md` statuses.
- [ ] Verify no mocks, fake model responses, or unlabeled simulations remain in implementation paths.
- [ ] Verify local-first model backends are real and OpenAI is only an opt-in online fallback.
- [ ] Verify no new security pragmas, blanket ignores, or quality bypasses were introduced.
- [ ] Verify UI behavior and wording do not overclaim missing spec features.
- [ ] Verify implemented behavior is traceable to M01-M13, X01-X04, `CAPABILITY_CONTRACT.md`, and `GLOSSARY.md`.
- [ ] Run all requested checks.
- [ ] Commit and push to the Hugging Face Space.
