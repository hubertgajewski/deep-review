#!/usr/bin/env python3
"""Publish immutable generic-package assets and idempotently create a GitLab Release."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


TAG_PATTERN = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_API_RESPONSE_BYTES = 1024 * 1024
RELEASE_CONTRACT = Path(__file__).resolve().parents[1] / "release-contract.json"
TRUSTED_GITLAB_ORIGIN = ("https", "gitlab.com", 443)


class PublishError(RuntimeError):
    """A safe, actionable publication failure."""


def _validated_https_url(label: str, value: str) -> tuple[str, str, int]:
    parsed = urlparse(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise PublishError(f"{label} must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise PublishError(f"{label} must not contain user information")
    if parsed.query or parsed.fragment:
        raise PublishError(f"{label} must not contain a query or fragment")
    try:
        port = parsed.port or 443
    except ValueError as error:
        raise PublishError(f"{label} contains an invalid port") from error
    return parsed.scheme.lower(), parsed.hostname.lower(), port


def release_asset_names(tag: str) -> tuple[str, ...]:
    try:
        contract = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublishError("release-contract.json is unavailable or malformed") from error
    if not isinstance(contract, dict) or contract.get("version") != 1:
        raise PublishError("release-contract.json has an unsupported version")
    templates = contract.get("release_assets")
    if not isinstance(templates, list) or not templates or any(
        not isinstance(template, str) for template in templates
    ):
        raise PublishError("release-contract.json has an invalid release_assets list")
    names = tuple(template.replace("{tag}", tag) for template in templates)
    if len(set(names)) != len(names) or any(
        not name or Path(name).name != name for name in names
    ):
        raise PublishError("release-contract.json produces unsafe or duplicate asset names")
    return names


class SafeRedirects(HTTPRedirectHandler):
    @staticmethod
    def _origin(url: str) -> tuple[str, str, int]:
        parsed = urlparse(url)
        try:
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        except ValueError as error:
            raise PublishError(f"GitLab API returned a redirect with an invalid port: {url}") from error
        return parsed.scheme.lower(), (parsed.hostname or "").lower(), port

    def redirect_request(
        self,
        request: Request,
        fp: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        if urlparse(new_url).scheme.lower() != "https":
            raise PublishError(f"GitLab API refused a non-HTTPS redirect from {request.full_url}")
        redirected = super().redirect_request(request, fp, code, message, headers, new_url)
        if redirected is not None and self._origin(request.full_url) != self._origin(new_url):
            redirected.headers.pop("Job-token", None)
            redirected.unredirected_hdrs.pop("Job-token", None)
        return redirected


URL_OPENER = build_opener(SafeRedirects())


def open_url(request: Request, *, timeout: int) -> Any:
    return URL_OPENER.open(request, timeout=timeout)


class GitLabClient:
    def __init__(
        self,
        api_url: str,
        project_id: str,
        project_url: str,
        job_token: str,
    ) -> None:
        api_origin = _validated_https_url("GitLab API URL", api_url)
        project_origin = _validated_https_url("GitLab project URL", project_url)
        if api_origin != TRUSTED_GITLAB_ORIGIN or project_origin != TRUSTED_GITLAB_ORIGIN:
            raise PublishError("GitLab API and project URLs must use https://gitlab.com")
        self.api_url = api_url.rstrip("/")
        self.project = quote(project_id, safe="")
        self.headers = {"JOB-TOKEN": job_token}

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        content_type: str | None = None,
        allow_not_found: bool = False,
        max_response_bytes: int = MAX_API_RESPONSE_BYTES,
    ) -> tuple[int, bytes]:
        headers = dict(self.headers)
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(f"{self.api_url}{path}", data=data, headers=headers, method=method)
        try:
            with open_url(request, timeout=60) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_length = int(content_length)
                    except ValueError as error:
                        raise PublishError(
                            f"GitLab API {method} {path} returned an invalid Content-Length"
                        ) from error
                    if declared_length < 0 or declared_length > max_response_bytes:
                        raise PublishError(
                            f"GitLab API {method} {path} response exceeds {max_response_bytes} bytes"
                        )
                body = response.read(max_response_bytes + 1)
                if len(body) > max_response_bytes:
                    raise PublishError(
                        f"GitLab API {method} {path} response exceeds {max_response_bytes} bytes"
                    )
                return response.status, body
        except HTTPError as error:
            body = error.read(MAX_API_RESPONSE_BYTES + 1).decode("utf-8", errors="replace")
            if allow_not_found and error.code == 404:
                return error.code, b""
            raise PublishError(
                f"GitLab API {method} {path} returned HTTP {error.code}: {body[:500]}"
            ) from error
        except URLError as error:
            raise PublishError(f"GitLab API {method} {path} failed: {error.reason}") from error

    def json_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> tuple[int, dict[str, Any] | list[Any] | None]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        status, body = self._request(
            method,
            path,
            data=data,
            content_type="application/json" if data is not None else None,
            allow_not_found=allow_not_found,
        )
        if status == 404 and allow_not_found:
            return status, None
        try:
            parsed = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PublishError(f"GitLab API {method} {path} returned malformed JSON") from error
        if not isinstance(parsed, (dict, list)):
            raise PublishError(f"GitLab API {method} {path} returned an unexpected JSON value")
        return status, parsed

    def publish_file(self, tag: str, path: Path) -> str:
        package_version = tag[1:]
        encoded_name = quote(path.name, safe="")
        package_path = (
            f"/projects/{self.project}/packages/generic/deep-review/"
            f"{quote(package_version, safe='')}/{encoded_name}"
        )
        if path.stat().st_size > MAX_ASSET_BYTES:
            raise PublishError(f"release asset {path.name} exceeds {MAX_ASSET_BYTES} bytes")
        local = path.read_bytes()
        status, remote = self._request(
            "GET", package_path, allow_not_found=True, max_response_bytes=len(local) + 1
        )
        if status == 200:
            if remote != local:
                raise PublishError(
                    f"durable asset {path.name} already exists with different content; "
                    "release assets are immutable"
                )
        else:
            self._request("PUT", package_path, data=local, content_type="application/octet-stream")
        return f"{self.api_url}{package_path}"

    def ensure_release(
        self,
        tag: str,
        project_url: str,
        assets: list[tuple[Path, str]],
    ) -> None:
        required_names = set(release_asset_names(tag))
        missing_names = sorted(required_names - {path.name for path, _ in assets})
        if missing_names:
            raise PublishError(
                "cannot publish install instructions without required assets: "
                + ", ".join(missing_names)
            )
        release_path = f"/projects/{self.project}/releases/{quote(tag, safe='')}"
        _, release = self.json_request("GET", release_path, allow_not_found=True)
        description = self._release_description(tag, project_url)
        if release is None:
            links = [self._link_payload(path, url) for path, url in assets]
            _, created = self.json_request(
                "POST",
                f"/projects/{self.project}/releases",
                payload={
                    "tag_name": tag,
                    "name": f"Deep Review {tag}",
                    "description": description,
                    "assets": {"links": links},
                },
            )
            if not isinstance(created, dict) or created.get("tag_name") != tag:
                raise PublishError("GitLab returned an invalid release after creation")
            return

        if not isinstance(release, dict):
            raise PublishError("GitLab returned an invalid existing release")
        release_assets = release.get("assets")
        existing_links = release_assets.get("links") if isinstance(release_assets, dict) else None
        if not isinstance(existing_links, list):
            raise PublishError("GitLab returned an existing release without an assets.links list")
        by_name = {
            item.get("name"): item
            for item in existing_links
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        links_path = f"{release_path}/assets/links"
        for path, url in assets:
            payload = self._link_payload(path, url)
            current = by_name.get(path.name)
            if current is None:
                self.json_request("POST", links_path, payload=payload)
                continue
            link_id = current.get("id")
            if not isinstance(link_id, int):
                raise PublishError(f"GitLab returned asset link {path.name} without a numeric id")
            if any(current.get(key) != value for key, value in payload.items()):
                self.json_request("PUT", f"{links_path}/{link_id}", payload=payload)
        self.json_request(
            "PUT",
            release_path,
            payload={"name": f"Deep Review {tag}", "description": description},
        )

    @staticmethod
    def _link_payload(path: Path, url: str) -> dict[str, str]:
        return {
            "name": path.name,
            "url": url,
            "direct_asset_path": f"/{path.name}",
            "link_type": "package",
        }

    @staticmethod
    def _release_description(tag: str, project_url: str) -> str:
        release = f"{project_url}/-/releases/{tag}/downloads"
        return f"""Deep Review {tag}

## Install

Paste the three commands for your operating system. The installer asks which AI client and scope to use and shows the destination before changing anything. It does not default to any client.

### Linux

```bash
( set -eu; install_dir="$(mktemp -d)"; trap 'rm -rf "$install_dir"' EXIT HUP INT TERM; curl --fail --fail-early --location --proto '=https' --tlsv1.2 --output "$install_dir/deep-review-install.sh" {release}/deep-review-install.sh --output "$install_dir/deep-review-install.sh.sha256" {release}/deep-review-install.sh.sha256 &&
(cd "$install_dir" && sha256sum -c deep-review-install.sh.sha256) &&
sh "$install_dir/deep-review-install.sh" )
```

### macOS

```bash
( set -eu; install_dir="$(mktemp -d)"; trap 'rm -rf "$install_dir"' EXIT HUP INT TERM; curl --fail --fail-early --location --proto '=https' --tlsv1.2 --output "$install_dir/deep-review-install.sh" {release}/deep-review-install.sh --output "$install_dir/deep-review-install.sh.sha256" {release}/deep-review-install.sh.sha256 &&
(cd "$install_dir" && shasum -a 256 -c deep-review-install.sh.sha256) &&
sh "$install_dir/deep-review-install.sh" )
```

The checksum command must print `deep-review-install.sh: OK` before the installer runs.

### Windows PowerShell

```powershell
& {{ $ErrorActionPreference = "Stop"; $installDir = Join-Path ([System.IO.Path]::GetTempPath()) ("deep-review-install-" + [guid]::NewGuid()); New-Item -ItemType Directory -Path $installDir | Out-Null; try {{ Invoke-WebRequest {release}/deep-review-install.ps1 -OutFile (Join-Path $installDir "deep-review-install.ps1"); Invoke-WebRequest {release}/deep-review-install.ps1.sha256 -OutFile (Join-Path $installDir "deep-review-install.ps1.sha256")
$expected = ((Get-Content (Join-Path $installDir "deep-review-install.ps1.sha256") -TotalCount 1) -split '\\s+')[0]; if ((Get-FileHash (Join-Path $installDir "deep-review-install.ps1") -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expected) {{ throw "Installer checksum verification failed" }}
& (Join-Path $installDir "deep-review-install.ps1") }} finally {{ Remove-Item -Recurse -Force -LiteralPath $installDir -ErrorAction SilentlyContinue }} }}
```

PowerShell stops before installation if a download fails or the checksum does not match. See the [installation guide]({project_url}/-/blob/{tag}/docs/installation.md) for automation, updates, and offline installation.
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-url", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--asset-directory", required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not TAG_PATTERN.fullmatch(args.tag):
        raise PublishError("tag must be an exact semantic version such as v1.1.0")
    required_names = release_asset_names(args.tag)
    asset_directory = Path(args.asset_directory)
    files = [asset_directory / name for name in required_names]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise PublishError(f"release asset does not exist: {', '.join(missing)}")

    job_token = os.environ.get("CI_JOB_TOKEN")
    if not job_token:
        raise PublishError("CI_JOB_TOKEN is required")
    client = GitLabClient(args.api_url, args.project_id, args.project_url, job_token)
    published = [(path, client.publish_file(args.tag, path)) for path in files]
    client.ensure_release(args.tag, args.project_url.rstrip("/"), published)
    print(f"Published {len(files)} durable assets for {args.tag}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, PublishError) as error:
        print(f"publish_release.py: {error}", file=sys.stderr)
        sys.exit(1)
