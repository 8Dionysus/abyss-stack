# Tree of Sophia Foundation Laboratory

This part is the `abyss-stack` owner for bounded A/B/C experiments that turn
Tree of Sophia source witnesses into inspectable candidates without turning a
runtime result into philosophical authority.

## Route

```text
ToS source item + tracked sample plan + rights posture
  -> current machine-fit and storage/resource preflight
    -> frozen A/B/C experiment specification
      -> isolated local run artifacts
        -> metrics + manual source-visible review + error ledger
          -> candidate promotion, rejection, or unresolved result
            -> reviewed derivative may return to ToS with provenance
```

The source bytes remain in the operator-designated Tree of Sophia item
`payload/` route. This part records stable IDs and local references; it never
copies restricted source bytes into Git.

## Speaking topology

```text
tos-foundation-lab/
├── AGENTS.md
├── README.md
├── docs/
│   ├── EXPERIMENT_LAW.md
│   ├── MANUAL_REVIEW_PROTOCOL.md
│   └── RESOURCE_GATE.md
├── examples/
│   └── tos-foundation-suite.v1.json
├── schemas/
│   ├── experiment-suite.schema.json
│   ├── manual-review-receipt.schema.json
│   ├── ocr-render-manifest.schema.json
│   ├── run-receipt.schema.json
│   ├── runtime-manifest.schema.json
│   ├── source-visible-model-inspection.schema.json
│   ├── translation-lab-readiness.schema.json
│   ├── translation-source-human-review.schema.json
│   ├── translation-source-manifest.schema.json
│   ├── translation-source-model-inspection.schema.json
│   └── translation-source-review-manifest.schema.json
├── tests/
│   └── test_tos_foundation_lab.py
├── canonical_graph.py
├── granite_embedding_bridge.py
├── granite_retrieval.py
├── kraken_party_ocr.py
├── kraken_party_runtime.py
├── lexical_retrieval.py
├── native_structure.py
├── neo4j_bridge.py
├── neo4j_graph.py
├── ocr_render.py
├── oxigraph_bridge.py
├── oxigraph_graph.py
├── paddle_ocr.py
├── paddle_ocr_bridge.py
├── paddle_ocr_runtime.py
├── runtime_manifest.py
├── semantic_retrieval.py
├── tesseract_ocr.py
├── tesseract_runtime.py
├── translation_source.py
├── translation_lab_readiness.py
├── translation_source_review.py
└── tos_foundation_lab.py
```

## Storage routes

| Artifact | Route | Posture |
| --- | --- | --- |
| durable local run evidence | `/srv/abyss-machine/storage/artifacts/tree-of-sophia-foundation-lab/` | private runtime truth; never automatic source authority |
| regenerable caches | `/srv/abyss-machine/cache/ai/tree-of-sophia-foundation-lab/` | disposable after retention review |
| isolated runtimes | `/srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/` | host-managed, versioned, removable after retention review |
| large scratch | `/srv/abyss-machine/tmp/tree-of-sophia-foundation-lab/` | bounded temporary output with explicit cleanup plan |
| source works | Tree of Sophia `ToS/source-witnesses/**/items/*/payload/` | immutable read-only evidence, outside lab ownership |

## Operator entrypoint

The stable wrapper is `scripts/aoa-tos-foundation-lab`.

```bash
scripts/aoa-tos-foundation-lab validate
scripts/aoa-tos-foundation-lab inspect --experiment tos-ocr-foundation-v1
scripts/aoa-tos-foundation-lab preflight --experiment tos-ocr-foundation-v1 --variant A
```

`preflight` is read-only by default and emits a receipt to stdout. A later run
must preserve that receipt next to its artifacts and repeat the gate if machine
state is no longer current.

The first executable bounded lane is deterministic Structure A. Prepare its
run packet from a fresh preflight, then launch the actual work through the host
resource owner:

```bash
scripts/aoa-tos-foundation-lab execute-native-structure RUN_ROOT \
  --tree-repo-root /srv/AbyssOS/Tree-of-Sophia \
  --sample-plan /srv/AbyssOS/Tree-of-Sophia/ToS/source-witnesses/works/friedrich-nietzsche/also-sprach-zarathustra/gold-sets/foundation-pilot-v1/sample-plan.json
```

The command deliberately closes at `awaiting-manual-review`. Empty output,
OCR contamination, wrong reading order, and text-quality errors remain real
results; no automatic status turns native extraction into transcription.

`manual-review-receipt.schema.json` requires a real human identity and an
explicit human-presence attestation. Source-visible inspection performed by a
model goes instead to `model_inspection_refs` under the separate advisory
schema; it can find candidate defects but can never authorize promotion.

Translation begins with a distinct pre-draft source stage, not with a model.
It verifies the exact 30 German EPUB members, preserves the full automatic
page extraction, first body paragraph, and deterministic first-sentence
proposal, and binds every proposal to a page in the sibling image-container
PDF. The current `EPUB page N -> PDF page N+1` relation remains explicitly
`proposed-unverified`; the packet does not convert the automatic EPUB OCR into
German source truth.

```bash
scripts/aoa-tos-foundation-lab materialize-translation-source \
  --tree-repo-root /srv/AbyssOS/Tree-of-Sophia \
  --sample-plan /srv/AbyssOS/Tree-of-Sophia/ToS/source-witnesses/works/friedrich-nietzsche/also-sprach-zarathustra/gold-sets/foundation-pilot-v1/translation-samples.json \
  --anchors /srv/AbyssOS/Tree-of-Sophia/ToS/source-witnesses/works/friedrich-nietzsche/also-sprach-zarathustra/gold-sets/foundation-pilot-v1/translation-anchors.jsonl \
  --packet-id zarathustra-translation-source-v1-20260723 \
  --visual-item-ref tos.item.friedrich-nietzsche.also-sprach-zarathustra.de-naumann-1893.internet-archive-image-container-pdf \
  --visual-file-ref tos.file.sha256.61c947e5aff76a64d82600cc52dcb25ff1b5862530d3a99c96824da885c1e6cf \
  --visual-file-sha256 61c947e5aff76a64d82600cc52dcb25ff1b5862530d3a99c96824da885c1e6cf
```

The command writes only under the private host artifact route. Its source
review JSONL is an immutable blank template for two real human passes, not a
review receipt. A second template reserves the user's spoken/read-aloud layer
but keeps it blocked until the German transcription is double-checked and
keeps personal spoken experience separate from philological acceptance. The
recognized Russian translation is represented only by its already tracked
IDs and remains sealed: no comparator payload path or text is read or emitted.
Consequently human-only, AI-only, and AI+human translation drafts all remain
unstarted after this command.

The first real packet exposed why this source stage cannot be reduced to a
green extractor. Exhaustive source-visible model inspection of all 30
candidates classified 7 as usable only with limits, rejected 22, and left 1
uncertain. Nineteen candidates were headings, two were page-start sentence
tails, and five contained visible OCR contamination. The v1 selector is
therefore retained as a negative baseline, not corrected in place or admitted
to translation.

The packet builder now emits only mechanical warning signals: candidate
length, leading character class, short-unit posture, surface equality with the
tracked structural context, and the always-unresolved page-start boundary.
These signals make obvious hazards inspectable; they never decide heading,
sentence, transcription, or source acceptance. Older immutable packets remain
verifiable without the optional signals.

The separate tracked advisory receipt can be checked against the immutable
private packet without reading the sealed comparator:

```bash
scripts/aoa-tos-foundation-lab verify-translation-source-inspection \
  TRACKED_SELECTOR_INSPECTION \
  --manifest PRIVATE_TRANSLATION_SOURCE_MANIFEST
```

The verifier closes every inspection row over the packet ID, manifest,
candidate-set and plan hashes, exact fragment order, source anchor, visual PDF
page, candidate artifact, decision counts, and failure-mode counts. Its green
result proves receipt integrity only. The model inspection still has
`promotion_authorized: false`, and German source acceptance still requires a
real human source-visible pass.

The failed first review-render attempt is retained in the method account as a
manual-control finding: its wrapper reported success after invalid output-name
expansion, while the intended directory still contained only 6 of 30 pages
and a render was misrouted as `.png` into the repository worktree. File count
and SHA-256 checks exposed the mismatch; the corrected explicit-prefix retry
produced 30 of 30 pages and the duplicate was removed. Process exit alone is
not artifact truth.

The v2 successor no longer tries to repair automatic German text. It consumes
the Tree-owned `translation-source-review-plan.v2.json`, verifies all 30 EPUB
member hashes without extracting candidate strings, renders the 89 unique
previous/current/next PDF pages, and creates two local blind workbooks:

```bash
scripts/aoa-tos-foundation-lab materialize-translation-source-review \
  --tree-repo-root /srv/AbyssOS/Tree-of-Sophia \
  --review-plan /srv/AbyssOS/Tree-of-Sophia/ToS/source-witnesses/works/friedrich-nietzsche/also-sprach-zarathustra/gold-sets/foundation-pilot-v1/translation-source-review-plan.v2.json \
  --packet-id zarathustra-translation-source-review-v2-20260723
```

Pass 1 asks a real human to classify layout, locate a complete prose boundary,
and transcribe diplomatic German. Pass 2 is a separate source-visible
punctuation, orthography, lineation, furniture, and boundary verification. The
HTML files save local draft JSON only; they do not submit, accept, or promote
anything. Neither workbook contains the v1 candidate, its model decision, or
the recognized translation. The accompanying JSONL remains a blank template
with both human attestations false and source acceptance null.

Materialization is a host write and must run through the current
`abyss-machine` resource owner. Verify the complete packet separately:

```bash
scripts/aoa-tos-foundation-lab verify-translation-source-review \
  PRIVATE_REVIEW_PACKET/translation-source-review-manifest.json
```

The first real v2 materialization produced 30 units, 89 unique page PNGs, 94
files, and 45,034,156 bytes. Its manifest SHA-256 is
`8db6f88131355e858b861696899ae5edc37b238ec31493d898c559153010850c`;
the page-set SHA-256 is
`b4b0faa670693c4db07a1f6eed3bde3d9191c0cc24168139f39cdf64144ea038`.
The routed systemd service completed in 40.706 seconds with a 142.961 MiB
memory peak and zero swap. The initial sequential-render estimate of 96 MiB
was lower than the observed peak, so the host runtime profile learned a
178.701 MiB future estimate. Independent checks counted the actual files,
closed the rendered set against the frozen triplets, opened pages 56, 203, and
519, and found zero occurrences of all 30 exact v1 candidates or either
recognized-comparator identifier in the review surfaces. All 30 review rows
remain blank and unaccepted.

Before any human-only, AI-only, or AI-alternatives translation lane, run the
read-only operational gate against the Tree-owned laboratory plan and the
fixity-verified private source interface:

```bash
scripts/aoa-tos-foundation-lab gate-translation-lab \
  --tree-repo-root /srv/AbyssOS/Tree-of-Sophia \
  --laboratory-plan /srv/AbyssOS/Tree-of-Sophia/ToS/source-witnesses/works/friedrich-nietzsche/also-sprach-zarathustra/gold-sets/foundation-pilot-v1/translation-laboratory-plan.v1.json \
  --reference-register /srv/AbyssOS/Tree-of-Sophia/ToS/source-witnesses/works/friedrich-nietzsche/also-sprach-zarathustra/gold-sets/foundation-pilot-v1/translation-reference-register.v1.json \
  --source-review-manifest PRIVATE_REVIEW_PACKET/translation-source-review-manifest.json \
  --human-review-output OPTIONAL_COMPLETED_TWO_PASS_REVIEW.jsonl
```

The command exits `2` while the translation-draft gate is blocked, not green.
It independently validates the
Tree-owned 14-entry, nine-category, zero-admission reference register and then
re-verifies all 89 page artifacts, plan/manifest digests, comparator sealing, 30 ordered
review identities, both real-human attestations, reviewer/time/transcription
fields, the second pass's independent transcription and checks, and each
source decision. A blank template is valid evidence of zero completed human
work and therefore remains blocked. It can never start a model or write a
translation packet. Only an explicit `accept` counts toward the 30-unit gate;
`accept-with-limits`, uncertainty, rejection, or deferral requires resolution
or a superseding review unit before translation. Even after all 30 units are
accepted, it opens three separate, mutually blind pre-draft lanes: real-human
only, AI-only, and AI-alternative. Each must independently freeze the exact
morphology-to-interlinear sequence under the Tree-owned pre-draft contract;
machine findings cannot enter the human-only packet, and human editing cannot
enter either model packet. Human-only, AI-only, and machine-alternative draft
lanes remain blocked until their own pre-draft evidence is frozen.

OCR uses a shared-input stage before any contestant. The renderer validates
the frozen visual plan, independently resolves and checks all three source
PDFs, and creates 36 full-page 300 DPI RGB PNGs exactly once:

```bash
scripts/aoa-tos-foundation-lab materialize-ocr-render \
  --tree-repo-root /srv/AbyssOS/Tree-of-Sophia \
  --sample-plan /srv/AbyssOS/Tree-of-Sophia/ToS/source-witnesses/works/friedrich-nietzsche/also-sprach-zarathustra/gold-sets/foundation-pilot-v1/ocr-visual-samples.json \
  --render-id zarathustra-foundation-pilot-v1-render-20260722 \
  --tree-local-manifest /srv/AbyssOS/Tree-of-Sophia/ToS/source-witnesses/works/friedrich-nietzsche/also-sprach-zarathustra/gold-sets/foundation-pilot-v1/local-content/ocr/renders/render-manifest.v1.json
```

The command must itself be launched through the current `abyss-machine`
resource owner. The large PNGs remain under the host artifact root; the
gitignored ToS path receives only the identical small manifest whose
`artifact_root` points back to those bytes. Any partial/failed render keeps a
failure receipt and cannot enter A/B/C.

OCR A then requires an exact verified runtime manifest. `preflight` accepts
`--runtime-manifest`, verifies the complete isolated tree and command, and
only then may prepare the run:

```bash
scripts/aoa-tos-foundation-lab materialize-tesseract-runtime \
  --rpm-cache /srv/abyss-machine/cache/ai/tree-of-sophia-foundation-lab/tesseract-5.5.2-fc44/rpms

scripts/aoa-tos-foundation-lab preflight \
  --experiment tos-ocr-foundation-v1 --variant A \
  --runtime-manifest /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/tesseract-5.5.2-fc44/runtime-manifest.json

scripts/aoa-tos-foundation-lab execute-tesseract-ocr RUN_ROOT \
  --sample-plan TRACKED_OCR_VISUAL_PLAN \
  --render-manifest PRIVATE_FROZEN_RENDER_MANIFEST \
  --runtime-manifest VERIFIED_TESSERACT_RUNTIME_MANIFEST
```

Tesseract consumes the frozen PNG bytes directly with `deu` or `rus`, OEM 1,
PSM 3, no outside preprocessing, and a four-thread ceiling. Plain text, TSV,
hOCR, ALTO, engine confidence, timing, and full digests are retained. CER,
WER, reading-order accuracy, correction time, and any winner verdict remain
null until double-checked human gold exists. `compare-tesseract-ocr` compares
two complete runs by output bytes while explicitly excluding timing from the
repeatability identity.

OCR B admits exactly one frozen Kraken/Party candidate after A's retention
decision. Acquisition and runtime construction are separate so the network
phase cannot disappear inside an apparently offline run:

```bash
scripts/aoa-tos-foundation-lab freeze-kraken-party-acquisition \
  --wheel-cache CACHED_COMPLETE_WHEEL_SET \
  --party-source CLEAN_PARTY_C2589B1_CHECKOUT \
  --model CACHED_PARTY_V4_SAFETENSORS \
  --zenodo-record CACHED_ZENODO_20642057_RECORD \
  --output CACHED_ACQUISITION_RECEIPT \
  --owner-receipt OWNER_ACQUISITION_RECEIPT

scripts/aoa-tos-foundation-lab materialize-kraken-party-runtime \
  --acquisition-receipt CACHED_ACQUISITION_RECEIPT \
  --owner-receipt OWNER_RUNTIME_BUILD_RECEIPT

scripts/aoa-tos-foundation-lab preflight \
  --experiment tos-ocr-foundation-v1 --variant B \
  --runtime-manifest /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/kraken-7.0.2-party-c2589b1/runtime-manifest.json

scripts/aoa-tos-foundation-lab execute-kraken-party-ocr RUN_ROOT \
  --sample-plan TRACKED_OCR_VISUAL_PLAN \
  --render-manifest PRIVATE_FROZEN_RENDER_MANIFEST \
  --runtime-manifest /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/kraken-7.0.2-party-c2589b1/runtime-manifest.json
```

The exact lane is Kraken 7.0.2 baseline segmentation plus Party commit
`c2589b1b515ed690f883c6afaef6c01ce29bf72d`, Party base v4 model DOI
`10.5281/zenodo.20642057`, and CPU float32 recognition with batch size 1,
four threads, seed 42, deterministic mode, and explicit `deu`/`rus` line
conditioning. The runtime's small offline constructor adapter suppresses only
Party's redundant external pretrained initialization; the Kraken loader still
requires zero missing or unexpected Party v4 state keys.

Kraken writes UUID-bearing ALTO IDs. OCR B therefore retains and reports raw
byte hashes while repeat comparison separately canonicalizes the `Layout` and
reading order without `ID`, `REF`, or `TAGREFS`. `compare-kraken-party-ocr`
reports both canonical identity and raw-byte drift; it cannot turn UUID drift
into a byte-identical claim. The conditioned ALTO is retained separately
because Party's recognized ALTO may omit `TextLine LANG` even though language
conditioning was verified before decoder execution. CER, WER, reading order,
correction time, and quality ranking remain null pending real human gold.

OCR C admits one independently frozen PaddleOCR candidate after B's stop and
retention decision. Its network acquisition, offline runtime build, resource
preflight, and source-witness execution remain separate evidence stages:

```bash
scripts/aoa-tos-foundation-lab freeze-paddle-ocr-acquisition \
  --wheel-cache CACHED_COMPLETE_WHEEL_SET \
  --model-cache CACHED_THREE_MODEL_ARCHIVES \
  --output CACHED_ACQUISITION_RECEIPT \
  --owner-receipt OWNER_ACQUISITION_RECEIPT

scripts/aoa-tos-foundation-lab materialize-paddle-ocr-runtime \
  --acquisition-receipt CACHED_ACQUISITION_RECEIPT \
  --owner-receipt OWNER_RUNTIME_BUILD_RECEIPT

scripts/aoa-tos-foundation-lab preflight \
  --experiment tos-ocr-foundation-v1 --variant C \
  --runtime-manifest /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/paddleocr-3.7.0-paddlex-3.7.2-paddle-3.3.1-cpu/runtime-manifest.json

scripts/aoa-tos-foundation-lab execute-paddle-ocr RUN_ROOT \
  --sample-plan TRACKED_OCR_VISUAL_PLAN \
  --render-manifest PRIVATE_FROZEN_RENDER_MANIFEST \
  --runtime-manifest /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/paddleocr-3.7.0-paddlex-3.7.2-paddle-3.3.1-cpu/runtime-manifest.json
```

Use repeated `--sample-id` only for an explicitly bounded diagnostic over pages
that already belong to the frozen render packet. The runner still verifies the
full sample plan, render manifest, and every selected PNG digest; it records the
bounded scope and cannot silently present that result as the full variant.

The frozen lane is PaddleOCR 3.7.0, PaddleX 3.7.2, and PaddlePaddle CPU
3.3.1 with `PP-OCRv5_server_det`, `latin_PP-OCRv5_mobile_rec` for German,
and `eslav_PP-OCRv5_mobile_rec` for Russian. It runs the CPU
`paddle_static` engine with MKLDNN disabled, batch size 1, four threads, and
explicit detector resizing at `960/max`; orientation classification and
document unwarping are disabled. The exact pinned
stack failed model initialization through its oneDNN path but passed the same
two recognizer smokes with MKLDNN disabled, so this setting is part of the
experiment identity rather than a hidden fallback.

The retained R1 failure omitted the explicit resize arguments. PaddleOCR 3.7.0
therefore inherited its installed general OCR configuration of `64/min`; on the
first 2480×3509 page, preprocessing rounded the detector input to 2496×3520 and
the owner scope ended in a kernel OOM at 16.7G peak memory. That configuration
is rejected. A one-page `960/max` execution is the required falsification test
before either a full rerun or acquisition of a mobile detector is admitted.

Each page retains the native Paddle result, ordered text regions with scores
and polygons, plain recognized text, engine identity, timing, and complete
digests. `compare-paddle-ocr` separates the semantic region/text identity from
raw-byte identity so timestamps and diagnostic bytes cannot masquerade as
recognition drift. Confidence is diagnostic output, not accuracy; CER, WER,
reading order, correction time, and quality ranking remain null pending real
human gold and source-visible review.

Retrieval A consumes a preserved Structure A run plus the separately frozen,
local-only query content:

```bash
scripts/aoa-tos-foundation-lab execute-lexical-retrieval RUN_ROOT \
  --structure-run-root STRUCTURE_RUN_ROOT \
  --query-plan TRACKED_RETRIEVAL_PLAN \
  --query-content LOCAL_IGNORED_QUERY_CONTENT
```

The FTS database, query text, snippets, and rankings remain private runtime
artifacts. Missing lemma/sign fields, empty source passages, cross-language
failures, and unjudged hard negatives are reported rather than filled with
model guesses.

Retrieval B consumes the same passages and queries through the resident local
OVMS embedding, isolated Qdrant, RAG API, and Qwen3 reranking route:

```bash
scripts/aoa-tos-foundation-lab execute-semantic-retrieval RUN_ROOT \
  --structure-run-root STRUCTURE_RUN_ROOT \
  --query-plan TRACKED_RETRIEVAL_PLAN \
  --query-content LOCAL_IGNORED_QUERY_CONTENT \
  --collection UNIQUE_LOWERCASE_COLLECTION
```

The runner refuses non-local service URLs, captures live container/source and
model artifact digests, proves deletion and exact rebuild of the isolated
collection, measures a cold reranker request plus warm dense/reranked requests,
and retains the rebuilt collection only for manual review. Model-proposed hits
and hard-negative presence remain diagnostics, never relevance truth.

Retrieval C keeps the identical 24 non-empty passages and 20 frozen queries but
uses the independent IBM Granite Embedding 311M Multilingual R2 family through
its exact official INT8 OpenVINO export:

```bash
scripts/aoa-tos-foundation-lab execute-granite-retrieval RUN_ROOT \
  --structure-run-root STRUCTURE_RUN_ROOT \
  --query-plan TRACKED_RETRIEVAL_PLAN \
  --query-content LOCAL_IGNORED_QUERY_CONTENT \
  --runtime-python /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/granite-embedding-311m-multilingual-r2-44399559/bin/python \
  --runtime-manifest /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/granite-embedding-311m-multilingual-r2-44399559/runtime-manifest.json \
  --model-snapshot /srv/abyss-machine/cache/ai/huggingface/models--ibm-granite--granite-embedding-311m-multilingual-r2/snapshots/44399559930365213510b1ee2eb15ded83374f0e
```

The runtime bridge uses the model-card contract—shared passage/query encoding,
CLS pooling, L2 normalization, cosine ranking—and executes no remote model
code. It proves exact run-local index deletion/rebuild and captures model,
runtime, tokenizer, input, and runner digests. Repeated rankings and
model-proposed target presence are mechanical diagnostics only; NDCG,
hard-negative error rate, and human cost remain null until real review.

Graph A reads the frozen ToS claim set directly and answers the frozen graph
questions without installing a graph database:

```bash
scripts/aoa-tos-foundation-lab execute-canonical-graph RUN_ROOT \
  --tree-repo-root /srv/AbyssOS/Tree-of-Sophia \
  --claim-set TRACKED_GRAPH_CLAIMS \
  --query-plan TRACKED_GRAPH_QUERY_PLAN
```

It preserves claim nodes, four logical layers, alternative claim families,
maker/provenance/evidence routes, and explicit `unreviewed` state. Mechanical
trace closure is not a verdict that an edge is philosophically or
bibliographically true.

Graph B projects the same claim rows into a unique property namespace in the
resident Neo4j service:

```bash
scripts/aoa-tos-foundation-lab execute-neo4j-graph RUN_ROOT \
  --tree-repo-root /srv/AbyssOS/Tree-of-Sophia \
  --claim-set TRACKED_GRAPH_CLAIMS \
  --query-plan TRACKED_GRAPH_QUERY_PLAN \
  --lab-run UNIQUE_LOWERCASE_NAMESPACE
```

Credentials remain inside the resident `rag-api` container; no password is
written to an invocation or artifact. Lab-only labels and a unique `lab_run`
property isolate the projection in Neo4j Community's shared database. The
runner proves delete/rebuild, retains claim nodes and alternative families,
and requires every direct assertion relationship to carry its `claim_id`.

Graph C projects the identical frozen claim rows into a private, run-local RDF
dataset through the pinned host-managed PyOxigraph runtime:

```bash
scripts/aoa-tos-foundation-lab execute-oxigraph-graph RUN_ROOT \
  --tree-repo-root /srv/AbyssOS/Tree-of-Sophia \
  --claim-set TRACKED_GRAPH_CLAIMS \
  --query-plan TRACKED_GRAPH_QUERY_PLAN \
  --runtime-python /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/pyoxigraph-0.5.9/bin/python \
  --runtime-manifest /srv/abyss-machine/runtimes/tree-of-sophia-foundation-lab/pyoxigraph-0.5.9/runtime-manifest.json \
  --lab-run UNIQUE_LOWERCASE_DATASET_KEY
```

Each assertion has an explicit claim resource and its own named graph. Identity
references stay named nodes, literal claim objects stay RDF literals, and the
runner preserves maker, provenance-event, evidence, review-status, and
alternative-claim routes. It proves exact deletion and deterministic rebuild,
captures canonical N-Quads and SPARQL receipts, and retains the derived store
only for manual inspection. RDF-star is deliberately not treated as claim
authority.

Golden-kernel transfer is currently a frozen experiment specification, not an
executable result. Its Tree-owned `transfer-samples.json` must report a
satisfied kernel evidence gate before any A/B/C run is admitted. The current
plan is `blocked-not-run`: the three out-of-kernel pages are title-page scouts,
not content-bearing semantic targets; accepted source units, human kernel
gold, reviewed sign/translation packets, and target-text gold are all absent.

The eventual comparison keeps A without the kernel, B with general contracts
and neutral format examples only, and C with independently human-accepted
Zarathustra packets. All three must share the exact target units, model,
runtime, prompt shell, and decoding. Accuracy, speed, correction time,
traceability, hallucinated relations, reusable-sign utility, ontology
imposition, and machine cost are all required. Missing evidence remains
unmeasured rather than zero; no command may synthesize C from model-only
packets or title pages.

The semantic-annotation and LLM-assistance suite entries follow the same
source gate. Their Tree-owned `semantic-samples.json` and `llm-tasks.json`
currently contain zero tasks and report `blocked-not-materialized`. Each must
move to `ready` with 30/30 accepted German units, 15/15 double-checked human
gold units, and exactly 20 content-bearing tasks—10 random and 10 hard—before
the stack may preflight a variant.

## Authority boundary

A complete green lab packet can establish that a method ran as specified and
that its metrics were computed from named files. It cannot establish that the
text, translation, etymology, sign, concept, or graph edge is correct. Those
claims require the manual protocol and the stronger Tree of Sophia review
route.
