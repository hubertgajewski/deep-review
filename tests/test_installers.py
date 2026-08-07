from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest
from unittest import mock
from urllib.error import HTTPError
import zipfile


ROOT = Path(__file__).resolve().parents[1]
POSIX_INSTALLER = ROOT / "deep-review-install.sh"
POWERSHELL_INSTALLER = ROOT / "deep-review-install.ps1"
VERSION = "v1.1.0"

PUBLISH_SPEC = importlib.util.spec_from_file_location(
    "publish_release", ROOT / "scripts" / "publish_release.py"
)
assert PUBLISH_SPEC and PUBLISH_SPEC.loader
PUBLISH_RELEASE = importlib.util.module_from_spec(PUBLISH_SPEC)
PUBLISH_SPEC.loader.exec_module(PUBLISH_RELEASE)


class FakeResponse:
    def __init__(self, body: bytes = b"", status: int = 200) -> None:
        self.body = body
        self.status = status
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *unused: object) -> None:
        return None

    def read(self, maximum: int = -1) -> bytes:
        return self.body if maximum < 0 else self.body[:maximum]


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="deep review installer ")
        self.root = Path(self.temporary.name)
        self.assets = self.root / "release assets"
        self.project = self.root / "project with spaces"
        self.home = self.root / "home with spaces"
        self.tempfiles = self.root / "temporary files"
        for path in (self.assets, self.project, self.home, self.tempfiles):
            path.mkdir()
        self.fake_bin = self.root / "fake bin"
        self.fake_bin.mkdir()
        self._create_assets()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _create_assets(self, *, include_agents: bool = True, manifest_version: str = "1.1.0") -> None:
        source = self.root / "package source" / "deep-review"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("---\nname: deep-review\n---\n", encoding="utf-8")
        for directory in ("references", "scripts"):
            path = source / directory
            path.mkdir()
            (path / "keep.txt").write_text(directory, encoding="utf-8")
        if include_agents:
            (source / "agents").mkdir()
            (source / "agents" / "openai.yaml").write_text("name: deep-review\n", encoding="utf-8")
        (source / ".claude-plugin").mkdir()
        (source / ".claude-plugin" / "plugin.json").write_text(
            f'{{\n  "version": "{manifest_version}"\n}}\n', encoding="utf-8"
        )

        tar_path = self.assets / f"deep-review-{VERSION}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as archive:
            archive.add(source, arcname="deep-review")
        zip_path = self.assets / f"deep-review-{VERSION}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in source.rglob("*"):
                archive.write(path, Path("deep-review") / path.relative_to(source))
        for path in (tar_path, zip_path):
            self._write_checksum(path)

    @staticmethod
    def _write_checksum(path: Path) -> None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_name(path.name + ".sha256").write_text(
            f"{digest}  {path.name}\n", encoding="ascii"
        )

    def _environment(self, **overrides: str) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update({"HOME": str(self.home), "TMPDIR": str(self.tempfiles)})
        environment.update(overrides)
        return environment

    def _run_posix(
        self,
        *arguments: str,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(POSIX_INSTALLER), *arguments],
            cwd=cwd or self.project,
            env=environment or self._environment(),
            text=True,
            capture_output=True,
            check=False,
        )

    def _run_powershell(
        self, *arguments: str, installer: Path = POWERSHELL_INSTALLER
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(installer), *arguments],
            cwd=self.project,
            env=self._environment(),
            text=True,
            capture_output=True,
            check=False,
        )

    def _run_powershell_with_failed_activation(
        self, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        wrapper = self.root / "fail activation.ps1"
        wrapper.write_text(
            """function Move-Item {
    [CmdletBinding()]
    param([string] $LiteralPath, [string] $Destination)
    if ($LiteralPath -like '*.deep-review.stage.*') { throw 'injected activation failure' }
    Microsoft.PowerShell.Management\\Move-Item -LiteralPath $LiteralPath -Destination $Destination
}
& $env:DEEP_REVIEW_INSTALLER_PATH @args
""",
            encoding="utf-8",
        )
        environment = self._environment(DEEP_REVIEW_INSTALLER_PATH=str(POWERSHELL_INSTALLER))
        return subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(wrapper), *arguments],
            cwd=self.project,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_posix_installs_project_package_and_reports_verification(self) -> None:
        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.project / ".agents" / "skills" / "deep-review"
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertTrue((destination / ".claude-plugin" / "plugin.json").is_file())
        self.assertIn(f"Installed Deep Review {VERSION}", result.stdout)
        self.assertIn(f"Destination: {destination.resolve()}", result.stdout)
        self.assertIn("Verification: SHA-256", result.stdout)
        self.assertIn("First review: $deep-review --base main", result.stdout)
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_maps_native_user_destination(self) -> None:
        result = self._run_posix(
            "--client", "cline", "--scope", "user", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / ".cline" / "skills" / "deep-review" / "SKILL.md").is_file())

    def test_posix_refuses_existing_destination_without_update(self) -> None:
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "existing.txt"
        marker.write_text("keep", encoding="utf-8")

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rerun with --update", result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_posix_update_replaces_complete_destination(self) -> None:
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "existing.txt"
        marker.write_text("replace", encoding="utf-8")

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets), "--update",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertTrue((destination / "SKILL.md").is_file())

    def test_posix_failed_activation_restores_existing_destination(self) -> None:
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "existing.txt"
        marker.write_text("keep", encoding="utf-8")
        fake_mv = self.fake_bin / "mv"
        fake_mv.write_text(
            """#!/bin/sh
case $1 in
    */.deep-review.stage.*) exit 1 ;;
esac
exec /bin/mv \"$@\"
""",
            encoding="utf-8",
        )
        fake_mv.chmod(0o755)
        environment = self._environment(PATH=f"{self.fake_bin}{os.pathsep}{os.environ['PATH']}")

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets), "--update", environment=environment,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not activate", result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertEqual(list(destination.parent.glob(".deep-review.backup.*")), [])
        self.assertFalse((destination.parent / ".deep-review.install.lock").exists())

    def test_posix_does_not_remove_another_installers_lock(self) -> None:
        parent = self.project / ".agents" / "skills"
        lock = parent / ".deep-review.install.lock"
        lock.mkdir(parents=True)
        owner = lock / "owner"
        owner.write_text("another installer", encoding="utf-8")

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another installation is active", result.stderr)
        self.assertEqual(owner.read_text(encoding="utf-8"), "another installer")

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_posix_update_refuses_symbolic_link_destination(self) -> None:
        target = self.root / "existing target"
        target.mkdir()
        marker = target / "existing.txt"
        marker.write_text("keep", encoding="utf-8")
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.parent.mkdir(parents=True)
        destination.symlink_to(target, target_is_directory=True)

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets), "--update",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symbolic link", result.stderr)
        self.assertTrue(destination.is_symlink())
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_posix_checksum_failure_leaves_destination_and_temporary_area_unchanged(self) -> None:
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "existing.txt"
        marker.write_text("keep", encoding="utf-8")
        checksum = self.assets / f"deep-review-{VERSION}.tar.gz.sha256"
        checksum.write_text(f"{'0' * 64}  deep-review-{VERSION}.tar.gz\n", encoding="ascii")

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets), "--update",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_missing_download_asset_leaves_no_destination(self) -> None:
        (self.assets / f"deep-review-{VERSION}.tar.gz").unlink()

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("offline archive not found", result.stderr)
        self.assertFalse((self.project / ".agents").exists())
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_online_download_uses_versioned_urls_and_cleans_failed_download(self) -> None:
        fake_curl = self.fake_bin / "curl"
        fake_curl.write_text(
            """#!/bin/sh
output=
url=
while [ \"$#\" -gt 0 ]; do
    case $1 in
        --output) output=$2; shift 2 ;;
        https://*) url=$1; shift ;;
        *) shift ;;
    esac
done
printf '%s\\n' \"$url\" >> \"$FAKE_CURL_LOG\"
if [ \"${FAKE_CURL_FAIL:-}\" = 1 ]; then
    printf partial > \"$output\"
    exit 22
fi
cp \"$FAKE_ASSETS/${url##*/}\" \"$output\"
""",
            encoding="utf-8",
        )
        fake_curl.chmod(0o755)
        log = self.root / "curl.log"
        environment = self._environment(
            PATH=f"{self.fake_bin}{os.pathsep}{os.environ['PATH']}",
            FAKE_ASSETS=str(self.assets),
            FAKE_CURL_LOG=str(log),
        )

        success = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            environment=environment,
        )
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(
            log.read_text(encoding="utf-8").splitlines(),
            [
                "https://gitlab.com/api/v4/projects/84183178/packages/generic/deep-review/"
                f"1.1.0/deep-review-{VERSION}.tar.gz",
                "https://gitlab.com/api/v4/projects/84183178/packages/generic/deep-review/"
                f"1.1.0/deep-review-{VERSION}.tar.gz.sha256",
            ],
        )

        shutil.rmtree(self.project / ".agents")
        failed = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            environment={**environment, "FAKE_CURL_FAIL": "1"},
        )
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("failed to download", failed.stderr)
        self.assertFalse((self.project / ".agents").exists())
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_rejects_incomplete_package_before_destination_mutation(self) -> None:
        shutil.rmtree(self.assets)
        self.assets.mkdir()
        shutil.rmtree(self.root / "package source")
        self._create_assets(include_agents=False)

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing deep-review/agents/", result.stderr)
        self.assertFalse((self.project / ".agents").exists())

    def test_posix_rejects_package_version_mismatch_before_destination_mutation(self) -> None:
        shutil.rmtree(self.assets)
        self.assets.mkdir()
        shutil.rmtree(self.root / "package source")
        self._create_assets(manifest_version="9.9.9")

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version does not match", result.stderr)
        self.assertFalse((self.project / ".agents").exists())

    def test_posix_rejects_archive_path_traversal_before_extraction(self) -> None:
        archive_path = self.assets / f"deep-review-{VERSION}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            entry = tarfile.TarInfo("deep-review/../../escaped.txt")
            entry.size = 7
            archive.addfile(entry, io.BytesIO(b"escaped"))
        self._write_checksum(archive_path)

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe path", result.stderr)
        self.assertFalse((self.project / ".agents").exists())
        self.assertFalse((self.tempfiles / "escaped.txt").exists())

    def test_posix_rejects_excessive_archive_entry_count(self) -> None:
        archive_path = self.assets / f"deep-review-{VERSION}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for index in range(10001):
                archive.addfile(tarfile.TarInfo(f"deep-review/entry-{index}"))
        self._write_checksum(archive_path)

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("10000-entry safety limit", result.stderr)
        self.assertFalse((self.project / ".agents").exists())

    def test_posix_rejects_excessive_expanded_size(self) -> None:
        large_file = self.root / "oversized sparse file"
        with large_file.open("wb") as stream:
            stream.seek(134217728)
            stream.write(b"0")
        archive_path = self.assets / f"deep-review-{VERSION}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(large_file, arcname="deep-review/oversized")
        self._write_checksum(archive_path)

        result = self._run_posix(
            "--client", "codex", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("134217728-byte extraction safety limit", result.stderr)
        self.assertFalse((self.project / ".agents").exists())

    def test_posix_stops_for_nondeterministic_client_without_mutation(self) -> None:
        result = self._run_posix(
            "--client", "t3", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no deterministic local destination", result.stderr)
        self.assertFalse((self.project / ".agents").exists())
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_claude_code_reports_native_skill_command(self) -> None:
        result = self._run_posix(
            "--client", "claude-code", "--scope", "project", "--version", VERSION,
            "--asset-dir", str(self.assets),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("First review: /deep-review --base main", result.stdout)

    def test_posix_rejects_noncanonical_versions_without_mutation(self) -> None:
        for invalid in ("1.1.0", "v01.1.0", "v1.1", "v1.1.0-rc1", "v1.1.0/../../x"):
            with self.subTest(invalid=invalid):
                result = self._run_posix(
                    "--client", "codex", "--scope", "project", "--version", invalid,
                    "--asset-dir", str(self.assets),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("semantic version", result.stderr)
        self.assertFalse((self.project / ".agents").exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_installs_path_with_spaces_and_preserves_hidden_metadata(self) -> None:
        result = self._run_powershell(
            "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.project / ".agents" / "skills" / "deep-review"
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertTrue((destination / ".claude-plugin" / "plugin.json").is_file())
        self.assertIn("Verification: SHA-256", result.stdout)
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_online_download_and_size_failure_are_transactional(self) -> None:
        assets = self.assets

        class AssetHandler(BaseHTTPRequestHandler):
            oversize = False
            requests: list[str] = []

            def do_GET(self) -> None:
                self.requests.append(self.path)
                name = self.path.rsplit("/", 1)[-1]
                path = assets / name
                if self.oversize and name.endswith(".zip"):
                    self.send_response(200)
                    self.send_header("Content-Length", "67108865")
                    self.end_headers()
                    return
                if not path.is_file():
                    self.send_error(404)
                    return
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *unused: object) -> None:
                return None

        server = ThreadingHTTPServer(("127.0.0.1", 0), AssetHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            test_installer = self.root / "online deep-review-install.ps1"
            source = POWERSHELL_INSTALLER.read_text(encoding="utf-8")
            test_base = f"http://127.0.0.1:{server.server_port}"
            test_installer.write_text(
                source.replace(
                    "https://gitlab.com/api/v4/projects/84183178/packages/generic/deep-review",
                    test_base,
                    1,
                ),
                encoding="utf-8",
            )

            success = self._run_powershell(
                "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
                installer=test_installer,
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual(
                AssetHandler.requests,
                [
                    f"/1.1.0/deep-review-{VERSION}.zip",
                    f"/1.1.0/deep-review-{VERSION}.zip.sha256",
                ],
            )

            shutil.rmtree(self.project / ".agents")
            AssetHandler.oversize = True
            failed = self._run_powershell(
                "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
                installer=test_installer,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("safety limit", failed.stderr)
            self.assertFalse((self.project / ".agents").exists())
            self.assertEqual(list(self.tempfiles.iterdir()), [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_refuses_existing_destination_and_checksum_failure(self) -> None:
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "existing.txt"
        marker.write_text("keep", encoding="utf-8")

        refused = self._run_powershell(
            "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets),
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

        checksum = self.assets / f"deep-review-{VERSION}.zip.sha256"
        checksum.write_text(f"{'0' * 64}  deep-review-{VERSION}.zip\n", encoding="ascii")
        corrupted = self._run_powershell(
            "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets), "-Update",
        )
        self.assertNotEqual(corrupted.returncode, 0)
        self.assertIn("Checksum verification failed", corrupted.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_update_replaces_complete_destination(self) -> None:
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "existing.txt"
        marker.write_text("replace", encoding="utf-8")

        result = self._run_powershell(
            "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets), "-Update",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertEqual(list(destination.parent.glob(".deep-review.backup.*")), [])
        self.assertFalse((destination.parent / ".deep-review.install.lock").exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_failed_activation_restores_existing_destination(self) -> None:
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "existing.txt"
        marker.write_text("keep", encoding="utf-8")

        result = self._run_powershell_with_failed_activation(
            "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets), "-Update",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("injected activation failure", result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertEqual(list(destination.parent.glob(".deep-review.backup.*")), [])
        self.assertFalse((destination.parent / ".deep-review.install.lock").exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_does_not_remove_another_installers_lock(self) -> None:
        parent = self.project / ".agents" / "skills"
        lock = parent / ".deep-review.install.lock"
        lock.mkdir(parents=True)
        owner = lock / "owner"
        owner.write_text("another installer", encoding="utf-8")

        result = self._run_powershell(
            "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another installation is active", result.stderr)
        self.assertEqual(owner.read_text(encoding="utf-8"), "another installer")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_stops_for_nondeterministic_client_without_mutation(self) -> None:
        result = self._run_powershell(
            "-Client", "t3", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no deterministic local destination", result.stderr)
        self.assertFalse((self.project / ".agents").exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_rejects_archive_path_traversal_before_extraction(self) -> None:
        archive_path = self.assets / f"deep-review-{VERSION}.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("deep-review/../../escaped.txt", "escaped")
        self._write_checksum(archive_path)

        result = self._run_powershell(
            "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe path", result.stderr)
        self.assertFalse((self.project / ".agents").exists())
        self.assertFalse((self.tempfiles / "escaped.txt").exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_rejects_excessive_archive_entry_count(self) -> None:
        archive_path = self.assets / f"deep-review-{VERSION}.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for index in range(10001):
                archive.writestr(f"deep-review/entry-{index}", "")
        self._write_checksum(archive_path)

        result = self._run_powershell(
            "-Client", "codex", "-Scope", "Project", "-Version", VERSION,
            "-AssetDirectory", str(self.assets),
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("10000-entry safety limit", result.stderr)
        self.assertFalse((self.project / ".agents").exists())


class ReleasePublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="deep review publisher ")
        self.asset = Path(self.temporary.name) / "asset.bin"
        self.asset.write_bytes(b"durable release asset")
        required_names = (
            f"deep-review-{VERSION}.tar.gz",
            f"deep-review-{VERSION}.tar.gz.sha256",
            f"deep-review-{VERSION}.zip",
            f"deep-review-{VERSION}.zip.sha256",
            "deep-review-install.sh",
            "deep-review-install.sh.sha256",
            "deep-review-install.ps1",
            "deep-review-install.ps1.sha256",
        )
        self.release_assets: list[tuple[Path, str]] = []
        for name in required_names:
            path = Path(self.temporary.name) / name
            path.write_bytes(name.encode("ascii"))
            self.release_assets.append((path, f"https://gitlab.example/package/{name}"))
        self.client = PUBLISH_RELEASE.GitLabClient(
            "https://gitlab.example/api/v4", "group/project", "secret-job-token"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _existing_release(self) -> dict[str, object]:
        links = []
        for link_id, (path, url) in enumerate(self.release_assets, start=1):
            links.append(
                {
                    "id": link_id,
                    "name": path.name,
                    "url": url,
                    "direct_asset_path": f"/deep-review/{VERSION}/{path.name}",
                    "link_type": "package",
                }
            )
        return {"tag_name": VERSION, "assets": {"links": links}}

    def test_publish_file_uploads_missing_asset_without_exposing_token_in_url(self) -> None:
        not_found = HTTPError("https://example.invalid", 404, "missing", {}, io.BytesIO())
        with mock.patch.object(
            PUBLISH_RELEASE,
            "open_url",
            side_effect=[not_found, FakeResponse(status=201)],
        ) as opened:
            url = self.client.publish_file(VERSION, self.asset)
        not_found.close()

        self.assertEqual(
            url,
            "https://gitlab.example/api/v4/projects/group%2Fproject/packages/generic/"
            "deep-review/1.1.0/asset.bin",
        )
        self.assertEqual(opened.call_count, 2)
        get_request = opened.call_args_list[0].args[0]
        put_request = opened.call_args_list[1].args[0]
        self.assertEqual(get_request.method, "GET")
        self.assertEqual(put_request.method, "PUT")
        self.assertEqual(put_request.data, self.asset.read_bytes())
        self.assertEqual(put_request.headers["Job-token"], "secret-job-token")
        self.assertNotIn("secret-job-token", put_request.full_url)

    def test_publish_file_reuses_identical_asset_and_rejects_mutation(self) -> None:
        with mock.patch.object(
            PUBLISH_RELEASE, "open_url", return_value=FakeResponse(self.asset.read_bytes())
        ) as opened:
            self.client.publish_file(VERSION, self.asset)
        self.assertEqual(opened.call_count, 1)

        with mock.patch.object(
            PUBLISH_RELEASE, "open_url", return_value=FakeResponse(b"different")
        ):
            with self.assertRaisesRegex(PUBLISH_RELEASE.PublishError, "immutable"):
                self.client.publish_file(VERSION, self.asset)

    def test_api_responses_are_bounded_and_redirects_strip_cross_origin_credentials(self) -> None:
        with mock.patch.object(
            PUBLISH_RELEASE, "open_url", return_value=FakeResponse(b"too large")
        ):
            with self.assertRaisesRegex(PUBLISH_RELEASE.PublishError, "response exceeds"):
                self.client._request("GET", "/bounded", max_response_bytes=4)

        source_request = PUBLISH_RELEASE.Request(
            "https://gitlab.example/api/v4/projects/1", headers={"JOB-TOKEN": "secret"}
        )
        redirected = PUBLISH_RELEASE.SafeRedirects().redirect_request(
            source_request,
            None,
            302,
            "Found",
            {},
            "https://objects.example/asset",
        )
        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertNotIn("Job-token", redirected.headers)
        self.assertNotIn("Job-token", redirected.unredirected_hdrs)
        with self.assertRaisesRegex(PUBLISH_RELEASE.PublishError, "non-HTTPS redirect"):
            PUBLISH_RELEASE.SafeRedirects().redirect_request(
                source_request,
                None,
                302,
                "Found",
                {},
                "http://objects.example/asset",
            )

    def test_release_creation_attaches_versioned_direct_links(self) -> None:
        self.client.json_request = mock.Mock(
            side_effect=[(404, None), (201, {"tag_name": VERSION})]
        )

        self.client.ensure_release(
            VERSION,
            "https://gitlab.example/group/project",
            self.release_assets,
        )

        create_call = self.client.json_request.call_args_list[1]
        self.assertEqual(create_call.args[0], "POST")
        payload = create_call.kwargs["payload"]
        link = payload["assets"]["links"][0]
        self.assertEqual(
            link["direct_asset_path"],
            f"/deep-review/{VERSION}/{self.release_assets[0][0].name}",
        )
        self.assertEqual(link["link_type"], "package")
        self.assertEqual(len(payload["assets"]["links"]), 8)
        description = payload["description"]
        for artifact in (
            "deep-review-install.sh",
            "deep-review-install.sh.sha256",
            "deep-review-install.ps1",
            "deep-review-install.ps1.sha256",
        ):
            self.assertIn(
                f"releases/{VERSION}/downloads/deep-review/{VERSION}/{artifact}",
                description,
            )
        self.assertIn("sha256sum -c deep-review-install.sh.sha256", description)
        self.assertIn("-split '\\s+'", description)
        self.assertIn("deep-review-install.sh --client codex --scope user --version", description)
        self.assertIn("$installer -Client codex -Scope User -Version", description)

    def test_release_posix_block_fails_closed_in_private_temporary_directory(self) -> None:
        description = self.client._release_description(
            VERSION, "https://gitlab.example/group/project"
        )
        block = description.split("```bash\n", 1)[1].split("\n```", 1)[0]
        with tempfile.TemporaryDirectory(prefix="release block ") as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_curl = fake_bin / "curl"
            fake_curl.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
            fake_curl.chmod(0o755)
            marker = root / "stale-installer-ran"
            (root / "deep-review-install.sh").write_text(
                f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8"
            )
            temporary_root = root / "temporary"
            temporary_root.mkdir()
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                    "TMPDIR": str(temporary_root),
                }
            )

            result = subprocess.run(
                ["sh", "-c", block],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertEqual(list(temporary_root.iterdir()), [])

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_release_powershell_block_fails_closed_in_private_temporary_directory(self) -> None:
        description = self.client._release_description(
            VERSION, "https://gitlab.example/group/project"
        )
        block = description.split("```powershell\n", 1)[1].split("\n```", 1)[0]
        with tempfile.TemporaryDirectory(prefix="release block ") as temporary:
            root = Path(temporary)
            marker = root / "stale-installer-ran"
            preference_marker = root / "preference-preserved"
            (root / "deep-review-install.ps1").write_text(
                f"Set-Content -LiteralPath '{marker}' -Value ran\n", encoding="utf-8"
            )
            temporary_root = root / "temporary"
            temporary_root.mkdir()
            environment = os.environ.copy()
            environment.update(
                {
                    "PREFERENCE_MARKER": str(preference_marker),
                    "TMPDIR": str(temporary_root),
                }
            )
            injected_failure = """
function Invoke-WebRequest {
    [CmdletBinding()]
    param([string] $Uri, [string] $OutFile)
    throw "injected download failure"
}
$ErrorActionPreference = "Continue"
try {
"""
            verify_preference = """
}
catch {
    if ($ErrorActionPreference -eq "Continue") {
        Set-Content -LiteralPath $env:PREFERENCE_MARKER -Value preserved
    }
    throw
}
"""

            result = subprocess.run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-Command",
                    injected_failure + block + verify_preference,
                ],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertTrue(preference_marker.is_file())
            self.assertEqual(list(temporary_root.iterdir()), [])

    def test_existing_release_is_updated_without_duplicate_asset_links(self) -> None:
        existing = self._existing_release()
        self.client.json_request = mock.Mock(side_effect=[(200, existing), (200, existing)])

        self.client.ensure_release(
            VERSION,
            "https://gitlab.example/group/project",
            self.release_assets,
        )

        self.assertEqual(self.client.json_request.call_count, 2)
        self.assertEqual(self.client.json_request.call_args_list[1].args[0], "PUT")

    def test_existing_release_publishes_install_description_only_after_link_repair(self) -> None:
        for mode in ("missing", "stale"):
            with self.subTest(mode=mode):
                existing = self._existing_release()
                links = existing["assets"]["links"]
                assert isinstance(links, list)
                if mode == "missing":
                    links.pop(0)
                    expected_method = "POST"
                    expected_path = (
                        f"/projects/{self.client.project}/releases/{VERSION}/assets/links"
                    )
                else:
                    links[0]["url"] = "https://gitlab.example/wrong"
                    expected_method = "PUT"
                    expected_path = (
                        f"/projects/{self.client.project}/releases/{VERSION}/assets/links/1"
                    )
                self.client.json_request = mock.Mock(
                    side_effect=[
                        (200, existing),
                        PUBLISH_RELEASE.PublishError("injected link failure"),
                    ]
                )

                with self.assertRaisesRegex(PUBLISH_RELEASE.PublishError, "injected link failure"):
                    self.client.ensure_release(
                        VERSION,
                        "https://gitlab.example/group/project",
                        self.release_assets,
                    )

                self.assertEqual(self.client.json_request.call_count, 2)
                mutation = self.client.json_request.call_args_list[1]
                self.assertEqual(mutation.args, (expected_method, expected_path))

    def test_release_instructions_require_every_installation_asset(self) -> None:
        self.client.json_request = mock.Mock()

        with self.assertRaisesRegex(PUBLISH_RELEASE.PublishError, "required assets"):
            self.client.ensure_release(
                VERSION,
                "https://gitlab.example/group/project",
                self.release_assets[:-1],
            )

        self.client.json_request.assert_not_called()

    def test_null_release_shape_fails_closed(self) -> None:
        self.client.json_request = mock.Mock(return_value=(200, []))
        with self.assertRaisesRegex(PUBLISH_RELEASE.PublishError, "invalid existing release"):
            self.client.ensure_release(
                VERSION,
                "https://gitlab.example/group/project",
                self.release_assets,
            )


if __name__ == "__main__":
    unittest.main()
