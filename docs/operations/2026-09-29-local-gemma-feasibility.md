# Local Gemma feasibility check — 2026-09-29

This was an isolated, offline feasibility experiment, not an advisory deployment or training run. It preserves the authority boundary in `docs/superpowers/specs/2026-08-13-rc-thermal-model-design.md`: a language model may propose or explain, but cannot command OpenHAB or actuators.

## Host and trial

- Host had approximately 15 GiB RAM, 7 GiB available, no detected GPU, and no active swapping during the initial check. These are point-in-time observations, not a guaranteed capacity budget.
- `gemma3:1b` (Ollama's 815 MB Q4 model) ran in a disposable Docker container with no network, 2 CPU limit, 3 GiB memory limit, no cloud access, and no connection to OpenHAB. Prompts contained only a sanitized thermal status summary, not private history or credentials.
- First response completed in about 2.5 seconds but replied `suggest_review` to low-confidence, reconstructed-label, null-candidate evidence and ignored the requested JSON shape.
- A second response with explicit abstention rules and JSON mode completed in about 3.5 seconds but returned `{"decision":"abstaint"}`, an invalid decision token. These two probes establish CPU inference feasibility, **not** model reliability or operational suitability.
- The exact disposable container, downloaded image, and temporary directory were removed after the trial. No AI service or collector was enabled.

## Recommended next gate

Keep the existing numerical thermal/PV models as the forecast and counterfactual authorities. Build a shadow-only candidate on *curated, timestamped* sensor/action/outcome examples; require strict schema validation, deterministic abstention on missing or low-quality evidence, and no tool/actuator access. Store input provenance, model/prompt versions, proposal, validator result, and later measured outcome. Evaluate chronologically against the RC model and simple seasonal rules before considering any fine-tuning.

Gemma's weights can be adapted with LoRA/PEFT once sufficiently many confirmed examples and clean outcomes exist. This host is adequate for testing a small quantized model's **inference**, but local fine-tuning is not recommended on its current no-GPU configuration. Training from scratch is out of scope. A temporary GPU machine can be assessed later against actual dataset size and model choice; no hardware purchase is warranted yet.

Moving native OpenHAB to Docker solely for backups is not recommended. It would still require backing up persistent configuration, userdata, add-ons, secrets, external PostgreSQL, and host scripts, while adding container/device/network and runtime-dependency qualification. First improve and verify native/off-host backups and restore rehearsal. Any future container migration needs its own attended plan and control-path tests.
