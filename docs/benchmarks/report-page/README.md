# The evaluation report, as a page

Source for **<https://sahayak-e2b-benchmark.vercel.app/>** — the same record as the Markdown documents in
the parent directory, laid out as a single readable page.

| File | What it is |
|---|---|
| `index.html` | The whole page. One file, no build step, no framework, no runtime dependency other than the Google Fonts stylesheet. |
| `tokens.css` | The design tokens as a portable export. Mirrors the `:root` block in `index.html`, which is authoritative. |

## Run it locally

Open `index.html` in a browser. That is the entire procedure — there is nothing to install.

Without a network the Google Fonts request fails and the page falls back to `ui-sans-serif` /
`ui-monospace`. Layout, contrast, and the stacked-table behaviour are unaffected.

## What the page is for

The Markdown documents are the record. The page exists because the *structure* of the evidence is itself
part of the argument, and a page can carry it in a way a list of files cannot:

- Every claim is stamped **[R]** reproducible, **[H]** human-graded, or **[M]** measured-once, with the
  legend at the top before any number appears.
- The strongest reproducible result leads. The most quotable number — the rubric accuracy — is presented
  *below* it with its three problems attached.
- The negative results and the reviewer critique are sections of the page, not an appendix.

## Verified at

320 / 375 / 414 / 768 / 1280 px. No horizontal overflow at any width; 309/309 text nodes meet WCAG AA
against their computed backgrounds; tables restructure into labelled cards below 768 px; the side rail
appears at 1024 px and up. Motion respects `prefers-reduced-motion`.

## Editing

`index.html` is a single file on purpose, and it is the source of truth. If you change a colour or a font,
change the token in the `:root` block and mirror it into `tokens.css` — no colour or `font-family` value
should ever appear outside that block.

If you change a **number**, run the verifier first:

```bash
python docs/benchmarks/verify_benchmarks.py
```

Every `[R]` figure on the page comes from that script's output. Numbers that the script cannot recompute
must not be labelled `[R]`.

## Deploy

Any static host. The production deployment is Vercel:

```bash
vercel deploy --prod
```

There is no build step and no output directory to configure.
