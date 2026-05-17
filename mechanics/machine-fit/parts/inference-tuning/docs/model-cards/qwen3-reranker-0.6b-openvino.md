# qwen3-reranker-0.6b-openvino

- `card_id`: `mc.qwen3-reranker-0.6b-openvino`
- `scope`: retrieval reranking lane for host-machine evidence and future stack RAG
- `status`: `host-validated-stack-candidate`
- `profile_class`: `retrieval`

## Best For

- host-machine evidence reranking after lexical and semantic retrieval
- bounded rerank candidate batches for nervous memory and future RAG routes
- Intel/OpenVINO canary use where a small fresh reranker is preferable to older cross-encoder families

## Avoid For

- treating the current artifact as a drop-in OVMS `/v3/rerank` model
- mixing rerank decisions into the `llama.cpp` text lane
- promoting rerank as a resident stack service before endpoint compatibility
  and retrieval-quality checks pass

## Preferred Backends

- host canary: Optimum Intel `OVModelForCausalLM` over the OpenVINO IR artifact
- future stack service: dedicated rerank wrapper or OVMS with a
  sequence-classification-compatible Qwen3 reranker artifact

## Validated Lanes

- host nervous rerank config:
  `/etc/abyss-machine/nervous/index.json`
- host model:
  `/srv/abyss-machine/cache/ai/qwen3-reranker-0.6b-int8-ov`
- host scorer:
  `/srv/abyss-machine/tools/ai/rerankers/qwen3_reranker_openvino_canary.py`

## Contract Notes

- The current host artifact is `OpenVINO/Qwen3-Reranker-0.6B-int8-ov`.
- That artifact is an OpenVINO CausalLM reranker and is compatible with
  OpenVINO 2026.0+ and Optimum Intel 1.27+.
- OVMS `/v3/rerank` supports rerank endpoints, but OVMS docs state that the
  original Qwen3 reranker is not supported directly and demonstrate a
  sequence-classification variant instead.
- Therefore stack promotion should use either:
  - a dedicated rerank API wrapper around the proven host scorer, or
  - a reviewed seq-cls Qwen3 reranker model served by OVMS.
- Keep embeddings and reranking separate: embeddings stay on OVMS today;
  reranking remains a separate retrieval-ranking lane.

## Evidence Surfaces

- latest host rerank eval: `/var/lib/abyss-machine/nervous/evals/rerank/latest.json`
- fresh eval snapshot: `/srv/abyss-machine/tmp/stack-reranker-next-rerank-eval.json`
- host canary artifacts: `/srv/abyss-machine/tmp/ai/rerankers/`
- OVMS rerank docs: https://docs.openvino.ai/nightly/model-server/ovms_demos_rerank.html
- model card: https://huggingface.co/OpenVINO/Qwen3-Reranker-0.6B-int8-ov

## Next Tests

1. Choose stack backend:
   - `rerank-api` wrapper over the host-proven scorer, or
   - OVMS seq-cls reranker artifact.
2. Run synthetic pairwise checks and live retrieval checks against stack inputs.
3. Verify that first-party machine evidence outranks clipboard/browser noise
   for machine queries.
4. Add `/rerank` or `/v3/rerank` smoke coverage only after endpoint semantics
   match the chosen backend.
