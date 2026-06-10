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

## Collaboration Rules

- Workers have disjoint write scopes.
- No worker may revert another worker's edits.
- Services do not import each other directly; they communicate through the bus.
- UI talks to the controller/facades, not directly to services.
- Phase 1 may simulate networking and local AI, but must label simulations honestly.
- Quality gates must be run before deployment.

## Integration Checklist

- [ ] Merge worker changes.
- [ ] Resolve conflicts without losing existing prototypes.
- [ ] Update `tasks.md` statuses.
- [ ] Run all requested checks.
- [ ] Commit and push to the Hugging Face Space.
