# Astra {{PACKAGE_NAME}} Docs

This is the public documentation repository for an Astra Unity package. It contains authored documentation, the public release lock, and the publishing workflow; it never contains private package source code or generated site output.

## Create a documentation project from this template

Use this procedure when adding documentation for a new package. It creates a public `ElectricDrillStudios/Astra<PackageName>Docs` repository from this template, configures its public identity and release lock, adds the read-only source token as a repository secret, enables GitHub Pages, and pushes the initial configuration.

### Prerequisites

Before creating the first project, prepare the shared publishing environment:

- A protected Linux self-hosted GitHub Actions runner registered to the `ElectricDrillStudios` organization, with the `astra-unity` label. Install the supported Unity LTS editor, Git, Python 3.11 or later, and .NET SDK 8 on that machine. The standard publishing host is `Cis8/AstraPublishingHost`.
- Restrict the runner group to trusted `Astra*Docs` repositories only. Because the documentation repositories are public and the runner consumes a secret, protect `main` so that only trusted maintainers can push to it or change workflows.
- The `ElectricDrillStudios/AstraDocsTemplate` GitHub repository must have **Template repository** enabled in its General settings.
- An authenticated GitHub CLI session that may create public repositories in `ElectricDrillStudios` and configure their Pages settings and secrets.
- A fine-grained personal access token named `ASTRA_SOURCE_READ_TOKEN`. Create it under the `Cis8` resource owner, grant it **Contents: Read-only**, and restrict it to `Cis8/AstraPublishingHost`, the target package repository, and any private Astra dependency repositories that may appear in the release lock. Use a short, manageable expiry. No write, Actions, Administration, or Workflow permission is needed.

Keep the token out of committed files, `.env` files, and `release-lock.yml`. If Unity opens the publishing host for the first time, commit the `.meta` files it creates to that private host repository.

### Bootstrap the repository

Clone this template repository and run the bootstrap command from that checkout. Replace the example values with the package's real identity and private source location.

```sh
git clone https://github.com/ElectricDrillStudios/AstraDocsTemplate.git
cd AstraDocsTemplate

export ASTRA_SOURCE_READ_TOKEN='github_pat_...'

python3 tools/astra_docs.py new Health \
  --package-id com.electricdrill.astra-health \
  --assembly com.electricdrill.astra-health.Runtime \
  --namespace 'ElectricDrill.Astra.Health' \
  --source-repo Cis8/AstraHealth \
  --source-path Packages/com.electricdrill.astra-health
```

`Health` must be a PascalCase name made from letters and digits. The command creates `ElectricDrillStudios/AstraHealthDocs` and a local `AstraHealthDocs` checkout inside the current directory. Omit `--source-path` only when the package lives at `Packages/<package-id>`. Use `--ref` to choose an initial source revision; it defaults to `main`. Use `--owner` only when the public repository belongs to a different GitHub organization or user.

The bootstrap command requires `ASTRA_SOURCE_READ_TOKEN`; it stores the value as a GitHub Actions secret in the new documentation repository, never in its tracked files. It also enables GitHub Pages with GitHub Actions as its build source.

### Finish repository configuration

In the new documentation repository, add this GitHub Actions repository variable:

- Name: `ASTRA_UNITY_PATH`
- Value: the absolute Unity executable path on the protected runner, for example `/opt/Unity/Hub/Editor/2022.3.62f1/Editor/Unity`.

Confirm that `ASTRA_SOURCE_READ_TOKEN` appears under Actions secrets and that GitHub Pages is configured to deploy from GitHub Actions. Apply branch protection to `main` before allowing routine contributions.

The new repository's `release-lock.yml` selects the primary package revision and is safe to review publicly: it names repositories, paths, assemblies, and revisions but contains no credentials or source files. Add every private Astra dependency under `dependencies` and its published documentation URL under `xref.astra` when cross-package API links are needed. Use `main` while developing; pin every `ref` to a tag or immutable commit SHA before a release.

### First publication

Commit authored Markdown and any lockfile edits, then validate the lock locally:

```sh
cd ../AstraHealthDocs
python3 tools/astra_docs.py validate
```

Push to `main` to publish automatically, or run the workflow manually from **Actions → Publish documentation → Run workflow**. The workflow checks out the private publishing host and the exact revisions from `release-lock.yml`, generates the site on the protected Unity runner, and uploads only the generated site to GitHub Pages.

Before the first release, run the package's API comparison spike: generate API metadata both from the Unity publishing host and from isolated sources, then compare their UIDs. Resolve any differences before pinning the release lock.

## Maintain an existing documentation repository

Validate the release lock before publishing or reviewing a change:

```sh
python3 tools/astra_docs.py validate
```

To adopt a newer version of the shared template files, first check the differences and then apply them deliberately:

```sh
python3 tools/astra_docs.py sync --check --template-ref v1.0.0
python3 tools/astra_docs.py sync --apply --template-ref v1.0.0
```

`sync` updates only the paths listed in `.astra-managed-files`. It preserves authored Markdown, images, `release-lock.yml`, and `astra-docs.json`.

Local, source-only DocFX previews are useful for experimentation, but release publications always use `Cis8/AstraPublishingHost` on the protected runner.
