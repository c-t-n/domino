# Publishing these docs

This documentation is built with [MkDocs](https://www.mkdocs.org/) and the
[Material](https://squidfunk.github.io/mkdocs-material/) theme. Everything is plain
Markdown under `docs/`, configured by `mkdocs.yml`.

## Preview locally

```bash
uv sync --group docs        # installs mkdocs-material into the project
uv run mkdocs serve         # live-reloading preview at http://127.0.0.1:8000
```

Edit any file under `docs/` and the browser refreshes automatically.

## Build the static site

```bash
uv run mkdocs build --strict   # outputs to site/ ; --strict fails on broken links
```

The generated `site/` directory is a self-contained static website you can host
anywhere.

## Publish to GitHub Pages

With the repository on GitHub, one command builds the site and pushes it to the
`gh-pages` branch:

```bash
uv run mkdocs gh-deploy
```

Then enable Pages for the `gh-pages` branch in the repository settings. Set
`site_url` (and, if you like, `repo_url`) in `mkdocs.yml` so links and the edit
button resolve correctly.

## Publish elsewhere

`site/` is just static files, so any static host works — Netlify, Cloudflare Pages,
S3 + CloudFront, GitLab Pages, or [Read the Docs](https://readthedocs.org/) (which
has native MkDocs support). Point the host at the repository and set the build
command to `mkdocs build`.
