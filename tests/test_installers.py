from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.error import HTTPError
import zipfile

try:
    import pty
except ImportError:  # pragma: no cover - Windows test hosts
    pty = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
POSIX_INSTALLER = ROOT / "deep-review-install.sh"
POWERSHELL_INSTALLER = ROOT / "deep-review-install.ps1"
VERSION = "v1.1.1"
RELEASE_CONTRACT = json.loads((ROOT / "release-contract.json").read_text(encoding="utf-8"))

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

    def _create_assets(self, *, include_agents: bool = True, manifest_version: str = "1.1.1") -> None:
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
        self,
        *arguments: str,
        installer: Path = POWERSHELL_INSTALLER,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(installer), *arguments],
            cwd=self.project,
            env=environment or self._environment(),
            text=True,
            capture_output=True,
            check=False,
        )

    def _run_interactive(
        self, command: list[str], answers: str
    ) -> tuple[int, str]:
        if pty is None:
            self.skipTest("pseudo-terminals are unavailable")
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(
                command,
                cwd=self.project,
                env=self._environment(),
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True,
            )
        finally:
            os.close(slave)
        os.set_blocking(master, False)
        os.write(master, answers.encode("utf-8"))
        output = bytearray()
        deadline = time.monotonic() + 10
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    process.kill()
                    self.fail("interactive installer did not finish within 10 seconds")
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                        if not chunk:
                            break
                        output.extend(chunk)
                    except (BlockingIOError, OSError):
                        break
            process.wait(timeout=5)
            while True:
                ready, _, _ = select.select([master], [], [], 0)
                if not ready:
                    break
                try:
                    chunk = os.read(master, 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                except (BlockingIOError, OSError):
                    break
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait()
        return process.returncode, output.decode("utf-8", errors="replace")

    def _run_powershell_wrapper(
        self, name: str, body: str, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        wrapper = self.root / name
        wrapper.write_text(body, encoding="utf-8")
        environment = self._environment(DEEP_REVIEW_INSTALLER_PATH=str(POWERSHELL_INSTALLER))
        return self._run_powershell(
            *arguments,
            installer=wrapper,
            environment=environment,
        )

    def _run_powershell_with_failed_activation(
        self, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return self._run_powershell_wrapper(
            "fail activation.ps1",
            """function Move-Item {
    [CmdletBinding()]
    param([string] $LiteralPath, [string] $Destination)
    if ($LiteralPath -like '*.deep-review.stage.*') { throw 'injected activation failure' }
    Microsoft.PowerShell.Management\\Move-Item -LiteralPath $LiteralPath -Destination $Destination
}
& $env:DEEP_REVIEW_INSTALLER_PATH @args
""",
            *arguments,
        )

    def _run_powershell_with_failed_backup_cleanup(
        self, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return self._run_powershell_wrapper(
            "fail backup cleanup.ps1",
            """function Remove-Item {
    [CmdletBinding()]
    param(
        [switch] $Recurse,
        [switch] $Force,
        [string] $LiteralPath
    )
    if ($LiteralPath -like '*.deep-review.backup.*') { throw 'injected backup cleanup failure' }
    Microsoft.PowerShell.Management\\Remove-Item @PSBoundParameters
}
& $env:DEEP_REVIEW_INSTALLER_PATH @args
""",
            *arguments,
        )

    def _installer_arguments(
        self, platform: str, *, client: str = "codex", update: bool = False
    ) -> tuple[str, ...]:
        if platform == "posix":
            arguments = (
                "--client", client, "--scope", "project", "--version", VERSION,
                "--asset-dir", str(self.assets),
            )
            return (*arguments, "--update") if update else arguments
        if platform == "powershell":
            arguments = (
                "-Client", client, "-Scope", "Project", "-Version", VERSION,
                "-AssetDirectory", str(self.assets),
            )
            return (*arguments, "-Update") if update else arguments
        raise ValueError(f"unsupported installer platform: {platform}")

    def _run_installer(
        self, platform: str, *, client: str = "codex", update: bool = False
    ) -> subprocess.CompletedProcess[str]:
        arguments = self._installer_arguments(platform, client=client, update=update)
        if platform == "posix":
            return self._run_posix(*arguments)
        return self._run_powershell(*arguments)

    def _existing_destination(self, marker_text: str) -> tuple[Path, Path]:
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "existing.txt"
        marker.write_text(marker_text, encoding="utf-8")
        return destination, marker

    def _run_with_failed_backup_cleanup(
        self, platform: str
    ) -> subprocess.CompletedProcess[str]:
        arguments = self._installer_arguments(platform, update=True)
        if platform == "powershell":
            return self._run_powershell_with_failed_backup_cleanup(*arguments)

        fake_rm = self.fake_bin / "rm"
        fake_rm.write_text(
            """#!/bin/sh
case "$*" in
    *'.deep-review.backup.'*) exit 1 ;;
esac
exec /bin/rm "$@"
""",
            encoding="utf-8",
        )
        fake_rm.chmod(0o755)
        environment = self._environment(PATH=f"{self.fake_bin}{os.pathsep}{os.environ['PATH']}")
        return self._run_posix(*arguments, environment=environment)

    def _run_with_failed_activation(self, platform: str) -> subprocess.CompletedProcess[str]:
        arguments = self._installer_arguments(platform, update=True)
        if platform == "powershell":
            return self._run_powershell_with_failed_activation(*arguments)

        fake_mv = self.fake_bin / "mv"
        fake_mv.write_text(
            """#!/bin/sh
case $1 in
    */.deep-review.stage.*) exit 1 ;;
esac
exec /bin/mv "$@"
""",
            encoding="utf-8",
        )
        fake_mv.chmod(0o755)
        environment = self._environment(PATH=f"{self.fake_bin}{os.pathsep}{os.environ['PATH']}")
        return self._run_posix(*arguments, environment=environment)

    def _write_adversarial_archive(self, platform: str, *, excessive_entries: bool) -> None:
        if platform == "posix":
            archive_path = self.assets / f"deep-review-{VERSION}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                if excessive_entries:
                    for index in range(10001):
                        archive.addfile(tarfile.TarInfo(f"deep-review/entry-{index}"))
                else:
                    entry = tarfile.TarInfo("deep-review/../../escaped.txt")
                    entry.size = 7
                    archive.addfile(entry, io.BytesIO(b"escaped"))
        else:
            archive_path = self.assets / f"deep-review-{VERSION}.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                if excessive_entries:
                    for index in range(10001):
                        archive.writestr(f"deep-review/entry-{index}", "")
                else:
                    archive.writestr("deep-review/../../escaped.txt", "escaped")
        self._write_checksum(archive_path)

    def _exercise_update_replacement(self, platform: str) -> None:
        destination, marker = self._existing_destination("replace")
        result = self._run_installer(platform, update=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertEqual(list(destination.parent.glob(".deep-review.backup.*")), [])
        self.assertFalse((destination.parent / ".deep-review.install.lock").exists())

    def _exercise_backup_cleanup_failure(self, platform: str) -> None:
        destination, _ = self._existing_destination("previous")
        result = self._run_with_failed_backup_cleanup(platform)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertFalse((destination / ".deep-review-installing").exists())
        backups = list(destination.parent.glob(".deep-review.backup.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "deep-review" / "existing.txt").read_text(), "previous")
        self.assertIn("installed successfully", (result.stdout + result.stderr).lower())

    def _exercise_failed_activation(self, platform: str) -> None:
        destination, marker = self._existing_destination("keep")
        result = self._run_with_failed_activation(platform)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "could not activate" if platform == "posix" else "injected activation failure",
            result.stderr,
        )
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertEqual(list(destination.parent.glob(".deep-review.backup.*")), [])
        self.assertFalse((destination.parent / ".deep-review.install.lock").exists())

    def _exercise_foreign_lock(self, platform: str) -> None:
        parent = self.project / ".agents" / "skills"
        lock = parent / ".deep-review.install.lock"
        lock.mkdir(parents=True)
        owner = lock / "owner"
        owner.write_text("another installer", encoding="utf-8")

        result = self._run_installer(platform)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another installation is active", result.stderr.lower())
        self.assertEqual(owner.read_text(encoding="utf-8"), "another installer")

    def _exercise_unsupported_client(self, platform: str) -> None:
        result = self._run_installer(platform, client="t3")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no deterministic local destination", result.stderr)
        self.assertFalse((self.project / ".agents").exists())

    def _exercise_linked_destination_ancestor(self, platform: str) -> None:
        external_root = self.root / "external agent root"
        destination = external_root / "skills" / "deep-review"
        destination.mkdir(parents=True)
        marker = destination / "trusted.txt"
        marker.write_text("preserve", encoding="utf-8")
        (self.project / ".agents").symlink_to(external_root, target_is_directory=True)

        result = self._run_installer(platform, update=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ancestor", result.stderr.lower())
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def _exercise_linked_destination(self, platform: str) -> None:
        target = self.root / "existing target"
        target.mkdir()
        marker = target / "existing.txt"
        marker.write_text("keep", encoding="utf-8")
        destination = self.project / ".agents" / "skills" / "deep-review"
        destination.parent.mkdir(parents=True)
        destination.symlink_to(target, target_is_directory=True)

        result = self._run_installer(platform, update=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symbolic link" if platform == "posix" else "reparse point", result.stderr)
        self.assertTrue(destination.is_symlink())
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def _exercise_adversarial_archive(self, platform: str, *, excessive_entries: bool) -> None:
        self._write_adversarial_archive(platform, excessive_entries=excessive_entries)
        result = self._run_installer(platform)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "10000-entry safety limit" if excessive_entries else "unsafe path",
            result.stderr,
        )
        self.assertFalse((self.project / ".agents").exists())
        if not excessive_entries:
            self.assertFalse((self.tempfiles / "escaped.txt").exists())

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

    def test_installers_match_versioned_client_contract(self) -> None:
        client_entries = " ".join(
            f"{client}={root}" for client, root in RELEASE_CONTRACT["client_roots"].items()
        )
        unsupported = " ".join(RELEASE_CONTRACT["unsupported_clients"])
        labels = "|".join(
            f"{client}={label}" for client, label in RELEASE_CONTRACT["client_labels"].items()
        )
        posix = POSIX_INSTALLER.read_text(encoding="utf-8")
        powershell = POWERSHELL_INSTALLER.read_text(encoding="utf-8")

        self.assertIn(f"CLIENT_ROOT_ENTRIES='{client_entries}'", posix)
        self.assertIn(f"UNSUPPORTED_CLIENTS='{unsupported}'", posix)
        self.assertIn(f"CLIENT_LABEL_ENTRIES='{labels}'", posix)
        self.assertIn(f'$ClientRootEntries = "{client_entries}"', powershell)
        self.assertIn(f'$ClientLabelEntries = "{labels}"', powershell)
        self.assertIn(f'$UnsupportedClientEntries = "{unsupported}"', powershell)
        self.assertEqual(
            list(RELEASE_CONTRACT["client_roots"]),
            list(RELEASE_CONTRACT["client_labels"]),
        )
        self.assertEqual(
            list(RELEASE_CONTRACT["client_labels"].values()),
            sorted(RELEASE_CONTRACT["client_labels"].values()),
        )
        manifest = json.loads(
            (ROOT / "skills" / "deep-review" / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(VERSION, f'v{manifest["version"]}')
        self.assertIn(f"version={VERSION}", posix)
        self.assertIn(f'[string] $Version = "{VERSION}"', powershell)

    def test_posix_explicit_automation_uses_embedded_version_without_prompting(self) -> None:
        result = self._run_posix(
            "--client", "claude-code", "--scope", "project",
            "--asset-dir", str(self.assets),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Installed Deep Review {VERSION}", result.stdout)
        self.assertTrue((self.project / ".claude" / "skills" / "deep-review" / "SKILL.md").is_file())

    def test_posix_noninteractive_mode_requires_client_and_scope_without_mutation(self) -> None:
        result = subprocess.run(
            ["sh", str(POSIX_INSTALLER), "--asset-dir", str(self.assets)],
            cwd=self.project,
            env=self._environment(),
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required in non-interactive mode", result.stderr)
        self.assertFalse((self.project / ".agents").exists())
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_guided_install_lists_clients_and_confirms_destination(self) -> None:
        status, output = self._run_interactive(
            ["sh", str(POSIX_INSTALLER), "--asset-dir", str(self.assets)],
            "claude-code\nproject\ny\n",
        )

        self.assertEqual(status, 0, output)
        self.assertIn("amp", output)
        self.assertIn("Amp", output)
        self.assertIn("codex", output)
        self.assertIn("Codex", output)
        destination = self.project / ".claude" / "skills" / "deep-review"
        self.assertIn(f"Destination: {destination.resolve()}", output)
        self.assertTrue((destination / "SKILL.md").is_file())

    def test_posix_guided_cancellation_changes_nothing(self) -> None:
        status, output = self._run_interactive(
            ["sh", str(POSIX_INSTALLER), "--asset-dir", str(self.assets)],
            "codex\nproject\nn\n",
        )

        self.assertNotEqual(status, 0)
        self.assertIn("installation cancelled", output)
        self.assertFalse((self.project / ".agents").exists())
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_guided_invalid_attempts_change_nothing(self) -> None:
        status, output = self._run_interactive(
            ["sh", str(POSIX_INSTALLER), "--asset-dir", str(self.assets)],
            "unknown\nt3\nnot-a-client\n",
        )

        self.assertNotEqual(status, 0)
        self.assertIn("after 3 attempts", output)
        self.assertFalse((self.project / ".agents").exists())
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_guided_eof_changes_nothing(self) -> None:
        status, output = self._run_interactive(
            ["sh", str(POSIX_INSTALLER), "--asset-dir", str(self.assets)],
            "\x04",
        )

        self.assertNotEqual(status, 0)
        self.assertIn("input ended", output)
        self.assertFalse((self.project / ".agents").exists())
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    def test_posix_guided_offline_update_reuses_verified_transaction(self) -> None:
        first = self._run_installer("posix", client="claude-code")
        self.assertEqual(first.returncode, 0, first.stderr)
        status, output = self._run_interactive(
            ["sh", str(POSIX_INSTALLER), "--update", "--asset-dir", str(self.assets)],
            "claude-code\nproject\ny\n",
        )

        self.assertEqual(status, 0, output)
        self.assertIn("Verification: SHA-256", output)
        destination = self.project / ".claude" / "skills" / "deep-review"
        self.assertTrue((destination / "SKILL.md").is_file())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_noninteractive_mode_requires_client_and_scope_without_mutation(self) -> None:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", str(POWERSHELL_INSTALLER),
             "-AssetDirectory", str(self.assets)],
            cwd=self.project,
            env=self._environment(),
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required in non-interactive mode", result.stderr)
        self.assertFalse((self.project / ".agents").exists())
        self.assertEqual(list(self.tempfiles.iterdir()), [])

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_guided_install_confirms_destination(self) -> None:
        status, output = self._run_interactive(
            ["pwsh", "-NoProfile", "-File", str(POWERSHELL_INSTALLER),
             "-AssetDirectory", str(self.assets)],
            "claude-code\nproject\ny\n",
        )

        self.assertEqual(status, 0, output)
        destination = self.project / ".claude" / "skills" / "deep-review"
        self.assertIn("Choose your AI client", output)
        self.assertIn(f"Destination: {destination.resolve()}", output)
        self.assertTrue((destination / "SKILL.md").is_file())

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
        self._exercise_update_replacement("posix")

    def test_posix_backup_cleanup_failure_keeps_successful_install(self) -> None:
        self._exercise_backup_cleanup_failure("posix")

    def test_posix_failed_activation_restores_existing_destination(self) -> None:
        self._exercise_failed_activation("posix")

    def test_posix_does_not_remove_another_installers_lock(self) -> None:
        self._exercise_foreign_lock("posix")

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_posix_update_refuses_symbolic_link_destination(self) -> None:
        self._exercise_linked_destination("posix")

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links are unavailable")
    def test_posix_update_refuses_symbolic_link_ancestor(self) -> None:
        self._exercise_linked_destination_ancestor("posix")

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
                f"{VERSION[1:]}/deep-review-{VERSION}.tar.gz",
                "https://gitlab.com/api/v4/projects/84183178/packages/generic/deep-review/"
                f"{VERSION[1:]}/deep-review-{VERSION}.tar.gz.sha256",
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
        self._exercise_adversarial_archive("posix", excessive_entries=False)

    def test_posix_rejects_excessive_archive_entry_count(self) -> None:
        self._exercise_adversarial_archive("posix", excessive_entries=True)

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
        self._exercise_unsupported_client("posix")
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
                    f"/{VERSION[1:]}/deep-review-{VERSION}.zip",
                    f"/{VERSION[1:]}/deep-review-{VERSION}.zip.sha256",
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
        self._exercise_update_replacement("powershell")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_backup_cleanup_failure_keeps_successful_install(self) -> None:
        self._exercise_backup_cleanup_failure("powershell")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_failed_activation_restores_existing_destination(self) -> None:
        self._exercise_failed_activation("powershell")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_does_not_remove_another_installers_lock(self) -> None:
        self._exercise_foreign_lock("powershell")

    @unittest.skipUnless(
        shutil.which("pwsh") and hasattr(os, "symlink"),
        "PowerShell or symbolic links are unavailable",
    )
    def test_powershell_update_refuses_symbolic_link_ancestor(self) -> None:
        self._exercise_linked_destination_ancestor("powershell")

    @unittest.skipUnless(
        shutil.which("pwsh") and hasattr(os, "symlink"),
        "PowerShell or symbolic links are unavailable",
    )
    def test_powershell_update_refuses_symbolic_link_destination(self) -> None:
        self._exercise_linked_destination("powershell")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_stops_for_nondeterministic_client_without_mutation(self) -> None:
        self._exercise_unsupported_client("powershell")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_rejects_archive_path_traversal_before_extraction(self) -> None:
        self._exercise_adversarial_archive("powershell", excessive_entries=False)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_powershell_rejects_excessive_archive_entry_count(self) -> None:
        self._exercise_adversarial_archive("powershell", excessive_entries=True)


class ReleasePublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="deep review publisher ")
        self.asset = Path(self.temporary.name) / "asset.bin"
        self.asset.write_bytes(b"durable release asset")
        required_names = PUBLISH_RELEASE.release_asset_names(VERSION)
        self.release_assets: list[tuple[Path, str]] = []
        for name in required_names:
            path = Path(self.temporary.name) / name
            path.write_bytes(name.encode("ascii"))
            self.release_assets.append((path, f"https://gitlab.com/package/{name}"))
        self.client = PUBLISH_RELEASE.GitLabClient(
            "https://gitlab.com/api/v4",
            "group/project",
            "https://gitlab.com/group/project",
            "secret-job-token",
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
                    "direct_asset_path": f"/{path.name}",
                    "link_type": "package",
                }
            )
        return {"tag_name": VERSION, "assets": {"links": links}}

    def test_client_rejects_untrusted_initial_urls_before_authentication(self) -> None:
        invalid = (
            ("http://gitlab.com/api/v4", "https://gitlab.com/group/project"),
            ("https://example.com/api/v4", "https://gitlab.com/group/project"),
            ("https://gitlab.com/api/v4", "https://example.com/group/project"),
            ("https://user@gitlab.com/api/v4", "https://gitlab.com/group/project"),
            ("https://gitlab.com/api/v4?target=other", "https://gitlab.com/group/project"),
        )
        for api_url, project_url in invalid:
            with self.subTest(api_url=api_url, project_url=project_url):
                with self.assertRaises(PUBLISH_RELEASE.PublishError):
                    PUBLISH_RELEASE.GitLabClient(
                        api_url, "group/project", project_url, "secret-job-token"
                    )

    def test_release_asset_roster_comes_from_versioned_contract(self) -> None:
        expected = tuple(
            template.replace("{tag}", VERSION)
            for template in RELEASE_CONTRACT["release_assets"]
        )
        self.assertEqual(PUBLISH_RELEASE.release_asset_names(VERSION), expected)
        self.assertEqual(tuple(path.name for path, _ in self.release_assets), expected)

    def test_publisher_requires_the_contract_owned_asset_directory(self) -> None:
        arguments = [
            "--api-url", "https://gitlab.com/api/v4",
            "--project-id", "group/project",
            "--project-url", "https://gitlab.com/group/project",
            "--tag", VERSION,
        ]

        with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
            PUBLISH_RELEASE.main(arguments)
        self.assertEqual(raised.exception.code, 2)

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
            "https://gitlab.com/api/v4/projects/group%2Fproject/packages/generic/"
            f"deep-review/{VERSION[1:]}/asset.bin",
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
            "https://gitlab.com/api/v4/projects/1", headers={"JOB-TOKEN": "secret"}
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
            "https://gitlab.com/group/project",
            self.release_assets,
        )

        create_call = self.client.json_request.call_args_list[1]
        self.assertEqual(create_call.args[0], "POST")
        payload = create_call.kwargs["payload"]
        link = payload["assets"]["links"][0]
        self.assertEqual(
            link["direct_asset_path"],
            f"/{self.release_assets[0][0].name}",
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
                f"releases/{VERSION}/downloads/{artifact}",
                description,
            )
        self.assertIn("sha256sum -c deep-review-install.sh.sha256", description)
        self.assertIn("--fail-early", description)
        self.assertIn("--proto '=https'", description)
        self.assertIn("-split '\\s+'", description)
        self.assertIn("sh ./deep-review-install.sh", description)
        self.assertIn("./deep-review-install.ps1", description)
        self.assertNotIn("codex", description.lower())

    def test_primary_documentation_matches_three_step_release_commands(self) -> None:
        description = self.client._release_description(
            VERSION, "https://gitlab.com/hubertgajewski-ai/deep-review"
        )
        installation = (ROOT / "docs" / "installation.md").read_text(encoding="utf-8")
        primary = installation.split("## Install from a release", 1)[1].split(
            "## Automated installation", 1
        )[0]

        for language, expected_count in (("bash", 2), ("powershell", 1)):
            pattern = rf"```{language}\n(.*?)\n```"
            release_blocks = re.findall(pattern, description, flags=re.DOTALL)
            documentation_blocks = re.findall(pattern, primary, flags=re.DOTALL)
            self.assertEqual(len(release_blocks), expected_count)
            self.assertEqual(documentation_blocks, release_blocks)
            for block in release_blocks:
                self.assertEqual(len(block.splitlines()), 3)

        for internal_detail in ("mktemp", "trap ", "installDirectory", "TemporaryRoot"):
            self.assertNotIn(internal_detail, primary)

    def test_release_posix_block_fails_closed_in_private_temporary_directory(self) -> None:
        description = self.client._release_description(
            VERSION, "https://gitlab.com/group/project"
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

    def test_release_posix_block_does_not_run_after_checksum_failure(self) -> None:
        description = self.client._release_description(
            VERSION, "https://gitlab.com/group/project"
        )
        block = description.split("```bash\n", 1)[1].split("\n```", 1)[0]
        with tempfile.TemporaryDirectory(prefix="release checksum block ") as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_curl = fake_bin / "curl"
            fake_curl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_curl.chmod(0o755)
            marker = root / "installer-ran"
            installer = root / "deep-review-install.sh"
            installer.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
            (root / "deep-review-install.sh.sha256").write_text(
                f"{'0' * 64}  deep-review-install.sh\n", encoding="ascii"
            )
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"

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

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not installed")
    def test_release_powershell_block_fails_closed_in_private_temporary_directory(self) -> None:
        description = self.client._release_description(
            VERSION, "https://gitlab.com/group/project"
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
            "https://gitlab.com/group/project",
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
                    links[0]["url"] = "https://gitlab.com/wrong"
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
                        "https://gitlab.com/group/project",
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
                "https://gitlab.com/group/project",
                self.release_assets[:-1],
            )

        self.client.json_request.assert_not_called()

    def test_null_release_shape_fails_closed(self) -> None:
        self.client.json_request = mock.Mock(return_value=(200, []))
        with self.assertRaisesRegex(PUBLISH_RELEASE.PublishError, "invalid existing release"):
            self.client.ensure_release(
                VERSION,
                "https://gitlab.com/group/project",
                self.release_assets,
            )


if __name__ == "__main__":
    unittest.main()
