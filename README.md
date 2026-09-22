# Astra {{PACKAGE_NAME}} Docs

This public repository contains written documentation and a public release lock. It intentionally does not contain package source code or generated site output.

## Publish

1. Update `release-lock.yml`. Use `main` for development; pin tags or commit SHAs for a release.
2. Validate and start the manually controlled publication:

   ```sh
   python tools/astra_docs.py publish
   ```

The workflow checks out the private Unity publishing host, materializes exactly the locked package revisions, generates project files with Unity, and uploads only `_site` to GitHub Pages.

## Maintain template files

```sh
python tools/astra_docs.py sync --check --template-ref v1.0.0
python tools/astra_docs.py sync --apply --template-ref v1.0.0
```

`sync` only updates the paths in `.astra-managed-files`. It preserves Markdown, images, `release-lock.yml`, and `astra-docs.json`.

Local, source-only DocFX previews are allowed for experimentation, but release publications always use `Cis8/AstraPublishingHost`.
