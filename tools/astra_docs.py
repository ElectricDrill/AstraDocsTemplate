#!/usr/bin/env python3
"""Bootstrap, validate, publish, and update Astra Docs repositories."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from lockfile import LockfileError, load_and_validate


ROOT = Path(__file__).resolve().parents[1]
TOKEN_NAME = "ASTRA_SOURCE_READ_TOKEN"
DEFAULT_OWNER = "ElectricDrillStudios"
DEFAULT_TEMPLATE = f"{DEFAULT_OWNER}/AstraDocsTemplate"
TEMPLATE_BRANCH = "main"


def run(*args: str, cwd: Path | None = None, secret: bool = False) -> None:
    print("+", "<redacted command>" if secret else " ".join(args))
    try:
        subprocess.run(args, cwd=cwd, check=True)
    except subprocess.CalledProcessError as error:
        if secret:
            raise RuntimeError("secret configuration command failed") from error
        raise


def wait_for_template_checkout(destination: Path, attempts: int = 30) -> None:
    """Wait for GitHub to make the generated template branch available."""
    for attempt in range(attempts):
        subprocess.run(
            ["git", "-C", str(destination), "fetch", "--quiet", "origin"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        available = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "--verify", f"origin/{TEMPLATE_BRANCH}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        if available:
            run("git", "-C", str(destination), "checkout", "--force", "-B", TEMPLATE_BRANCH, f"origin/{TEMPLATE_BRANCH}")
            return
        if attempt < attempts - 1:
            time.sleep(1)
    raise RuntimeError("the generated repository did not receive its template branch within 30 seconds")


def repository_exists(repository: str) -> bool:
    return subprocess.run(
        ["gh", "repo", "view", repository, "--json", "name"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def ensure_github_authentication() -> None:
    authenticated = subprocess.run(
        ["gh", "auth", "status", "--hostname", "github.com"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not authenticated:
        print("GitHub CLI is not authenticated; opening browser login...")
        run("gh", "auth", "login", "--hostname", "github.com", "--web", "--git-protocol", "https")
    run("gh", "auth", "setup-git")


def assert_clean_resume_checkout(destination: Path, repository: str) -> None:
    if not (destination / ".git").exists():
        raise ValueError(f"--resume requires a Git checkout at {destination}")
    remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=destination, text=True).strip().rstrip("/")
    expected = {
        f"https://github.com/{repository}.git",
        f"https://github.com/{repository}",
        f"git@github.com:{repository}.git",
        f"git@github.com:{repository}",
    }
    if remote not in expected:
        raise ValueError(f"--resume requires origin to point at {repository}, not {remote}")
    changes = subprocess.check_output(["git", "status", "--porcelain"], cwd=destination, text=True)
    if changes:
        raise ValueError(f"--resume refuses to overwrite local changes in {destination}")


def commit_configuration(destination: Path) -> None:
    run("git", "add", ".", cwd=destination)
    changes = subprocess.check_output(["git", "status", "--porcelain"], cwd=destination, text=True)
    if changes:
        run("git", "commit", "-m", "Configure Astra documentation", cwd=destination)
    else:
        print("configuration commit already exists")


def package_slug(name: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"-\1", name).lower()


def repository_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
        raise ValueError("package name must be PascalCase letters/digits (for example Health)")
    return f"Astra{name}Docs"


def read_config(root: Path) -> dict[str, str]:
    path = root / "astra-docs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {path}: {error}") from error
    for key in ("package_name", "title", "pages_url"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ValueError(f"astra-docs.json.{key} must be a non-empty string")
    return data


def render_template(source: Path, destination: Path, config: dict[str, str]) -> None:
    text = source.read_text(encoding="utf-8")
    text = (text.replace("{{TITLE}}", config["title"])
                .replace("{{PAGES_URL}}", config["pages_url"])
                .replace("{{PACKAGE_NAME}}", config["package_name"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def write_lock(root: Path, args: argparse.Namespace) -> None:
    lock = f"""# Public, reviewable input for one documentation/release build.\nversion: 1\npackage:\n  id: {args.package_id}\n  assembly: {args.assembly}\n  namespace: {args.namespace}\n  source:\n    repository: {args.source_repo}\n    path: {args.source_path}\n    files: Runtime/**/*.cs\n    ref: {args.ref}\ndependencies: []\nxref:\n  unity: https://normanderwan.github.io/UnityXrefMaps/xrefmap.yml\n  astra: []\n"""
    (root / "release-lock.yml").write_text(lock, encoding="utf-8")


def configure_new_repository(root: Path, args: argparse.Namespace) -> None:
    repo = repository_name(args.package_name)
    config = {
        "schema": 1,
        "package_name": args.package_name,
        "title": args.title or f"Astra {args.package_name}",
        "pages_url": f"https://{args.owner.lower()}.github.io/{repo}/",
    }
    (root / "astra-docs.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    render_template(root / "DocFx/docfx.json", root / "DocFx/docfx.json", config)
    render_template(root / "README.md", root / "README.md", config)
    write_lock(root, args)


def command_new(args: argparse.Namespace) -> None:
    if not os.environ.get(TOKEN_NAME):
        raise ValueError(f"set {TOKEN_NAME} to a fine-grained read-only contents token before bootstrapping")
    repo = repository_name(args.package_name)
    destination = Path(args.directory or repo).resolve()
    repository = f"{args.owner}/{repo}"
    ensure_github_authentication()
    if args.resume:
        if not repository_exists(repository):
            raise ValueError(f"cannot resume because GitHub repository does not exist: {repository}")
        if destination.exists():
            assert_clean_resume_checkout(destination, repository)
        else:
            run("git", "clone", f"https://github.com/{repository}.git", str(destination))
    else:
        if destination.exists():
            raise ValueError(f"destination already exists: {destination}; use --resume only for a failed bootstrap")
        if repository_exists(repository):
            raise ValueError(f"GitHub repository already exists: {repository}; use --resume only for a failed bootstrap")
        run("gh", "repo", "create", repository, "--public", "--template", args.template)
        run("git", "clone", f"https://github.com/{repository}.git", str(destination))
    wait_for_template_checkout(destination)
    configure_new_repository(destination, args)
    run("gh", "secret", "set", TOKEN_NAME, "--repo", repository, "--body", os.environ[TOKEN_NAME], secret=True)
    if args.unity_path:
        run("gh", "variable", "set", "ASTRA_UNITY_PATH", "--repo", repository, "--body", args.unity_path)
    # Create Pages configuration, or update it when this is a repeatable bootstrap.
    try:
        run("gh", "api", "--method", "POST", f"repos/{repository}/pages", "-f", "build_type=workflow")
    except subprocess.CalledProcessError:
        run("gh", "api", "--method", "PUT", f"repos/{repository}/pages", "-f", "build_type=workflow")
    commit_configuration(destination)
    run("git", "push", "origin", "main", cwd=destination)
    print(f"Created https://{args.owner.lower()}.github.io/{repo}/")


def command_validate(args: argparse.Namespace) -> None:
    lock = Path(args.lock).resolve()
    data = load_and_validate(lock)
    target = data["package"]
    print(f"valid: {target['id']} ({target['assembly']}) at {target['source']['repository']}@{target['source']['ref']}")


def command_publish(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    command_validate(argparse.Namespace(lock=root / "release-lock.yml"))
    remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=root, text=True).strip()
    match = re.search(r"(?:github.com[:/])([^/]+)/([^/.]+)(?:\.git)?$", remote)
    if not match:
        raise ValueError("origin must point at a GitHub repository")
    run("gh", "workflow", "run", "publish-docs.yml", "--repo", f"{match.group(1)}/{match.group(2)}", "--ref", "main")


def template_root(args: argparse.Namespace) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if args.template_path:
        return Path(args.template_path).resolve(), None
    temporary = tempfile.TemporaryDirectory(prefix="astra-template-")
    target = Path(temporary.name) / "template"
    run("git", "clone", "--quiet", f"https://github.com/{DEFAULT_TEMPLATE}.git", str(target))
    run("git", "checkout", "--quiet", args.template_ref, cwd=target)
    return target, temporary


def command_sync(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    config = read_config(root)
    source_root, temporary = template_root(args)
    try:
        managed = (source_root / ".astra-managed-files").read_text(encoding="utf-8").splitlines()
        changed: list[str] = []
        for relative in filter(None, managed):
            source = source_root / relative
            destination = root / relative
            if relative == "DocFx/docfx.json":
                expected = (source.read_text(encoding="utf-8").replace("{{TITLE}}", config["title"])
                            .replace("{{PAGES_URL}}", config["pages_url"])
                            .replace("{{PACKAGE_NAME}}", config["package_name"]))
                actual = destination.read_text(encoding="utf-8") if destination.exists() else ""
                different = expected != actual
            else:
                different = not destination.exists() or source.read_bytes() != destination.read_bytes()
            if different:
                changed.append(relative)
                if args.apply:
                    if relative == "DocFx/docfx.json":
                        render_template(source, destination, config)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, destination)
        if args.apply:
            (root / ".astra-template-version").write_text(args.template_ref + "\n", encoding="utf-8")
        if changed:
            print(("updated" if args.apply else "out of date") + ": " + ", ".join(changed))
            if not args.apply:
                raise SystemExit(1)
        else:
            print("template-managed files are current")
    finally:
        if temporary:
            temporary.cleanup()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    create = commands.add_parser("new", help="create and configure a public docs repository")
    create.add_argument("package_name")
    create.add_argument("--package-id", required=True)
    create.add_argument("--assembly", required=True)
    create.add_argument("--namespace", required=True)
    create.add_argument("--source-repo", required=True, help="private OWNER/REPOSITORY")
    create.add_argument("--source-path", help="path to the Unity package within the repository")
    create.add_argument("--ref", default="main")
    create.add_argument("--title")
    create.add_argument("--owner", default=DEFAULT_OWNER, help="GitHub organization or user that will own the public docs repository")
    create.add_argument("--template", default=DEFAULT_TEMPLATE)
    create.add_argument("--unity-path", help="single-runner override: absolute Unity executable path")
    create.add_argument("--directory")
    create.add_argument("--resume", action="store_true", help="continue a failed bootstrap for the same clean checkout")
    create.set_defaults(handler=command_new)
    validate = commands.add_parser("validate", help="validate a release lock without credentials")
    validate.add_argument("--lock", default="release-lock.yml")
    validate.set_defaults(handler=command_validate)
    publish = commands.add_parser("publish", help="validate then dispatch the publish workflow")
    publish.add_argument("--root", default=".")
    publish.set_defaults(handler=command_publish)
    sync = commands.add_parser("sync", help="update only template-managed files")
    mode = sync.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    sync.add_argument("--root", default=".")
    sync.add_argument("--template-ref", required=True)
    sync.add_argument("--template-path", help=argparse.SUPPRESS)
    sync.set_defaults(handler=command_sync)
    return result


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "command", None) == "new" and not args.source_path:
        args.source_path = f"Packages/{args.package_id}"
    try:
        args.handler(args)
    except (LockfileError, ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
