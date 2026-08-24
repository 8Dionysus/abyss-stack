# Diagnose Wrapper

Routes `scripts/aoa-diagnose`,
`mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.sh`,
`mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py`, and
`tests/test_aoa_diagnose.py`.

The wrapper produces bounded diagnosis artifacts and stays subordinate to the
diagnostic surface contracts.

## Source binding

The diagnostic fallback truth check follows the same bounded route as autonomy
status: explicit `AOA_SOURCE_ROOT` plus its absolute shared `AOA_SOURCE_IDENTITY`
receipt first, then a content-addressed identity derived from the executing owner
checkout. The receipt binds exact Git `HEAD`/tree coordinates and selected
source-surface digests; the source shape still requires the exact first
non-empty `README.md` line `# abyss-stack` and owner line 'Root route card for
`abyss-stack`.' in the first eight `AGENTS.md` lines. There is no home-directory,
sibling, workspace, or deployed `Configs` fallback. Relative or symlink aliases
are valid only under that identity contract, and the binding is revalidated
before the fallback truth is used. An invalid explicit binding is not replaced
silently.
When no valid source input exists, the diagnostic result preserves an explicit
`source_root_unresolved` truth gap; it does not convert source absence into
runtime health, deployment, or repair completion.
