from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from agent_experience import (
    MountPolicy,
    MountStatus,
    PackageSigner,
    Repository,
    TrustStatus,
    agent_experience,
)
from agent_experience.package import PackageService
from agent_experience.package.source import ResolvedPackage
from agent_experience.schema import events_pb2, experience_pb2, package_pb2

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


def portable_definition(
    *,
    revision: str = "revision-1",
    content: bytes = b"portable-content",
    capability: str = "capability://weather@1",
    experience_id: str = "source-experience",
) -> experience_pb2.ExperienceDefinition:
    return experience_pb2.ExperienceDefinition(
        experience_id=experience_id,
        revision_id=revision,
        generation=1,
        schema_version=1,
        content_hash=content,
        experience_type=experience_pb2.TASK_STRATEGY,
        status=experience_pb2.ACTIVE,
        summary="Use the weather capability and validate freshness",
        applicability=experience_pb2.Applicability(
            required_tools=[
                experience_pb2.ToolContract(
                    contract_id=capability,
                    name=capability.split("//", 1)[-1].split("@", 1)[0],
                    version_constraint=">=1,<2",
                )
            ]
        ),
    )


class PackageMountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_signed_one_line_mount_is_quarantined_and_reported(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            package = root / "weather.exp"
            signer = PackageSigner.generate()
            with Repository(root / "source") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=portable_definition(),
                )
                PackageService(source).export(
                    package,
                    name="weather-patterns",
                    version="1.0.0",
                    publisher="test-publisher",
                    signer=signer,
                )

            experience = agent_experience(root / "target")

            @experience.tool(capability="weather@1")
            def weather(city: str) -> str:
                return city

            report = experience.mount(package)
            self.assertEqual(report.status, MountStatus.MOUNTED_IN_QUARANTINE)
            self.assertEqual(report.trust, TrustStatus.SIGNED_UNKNOWN)
            self.assertEqual(report.imported, 1)
            self.assertEqual(report.compatible, 1)
            self.assertEqual(report.needs_binding, 0)
            self.assertIn("weather-patterns@1.0.0", str(report))
            imported = [
                event
                for event in experience.repository.events()
                if event.event_type == events_pb2.EXPERIENCE_IMPORTED
            ]
            self.assertEqual(len(imported), 1)
            definition = experience_pb2.ExperienceDefinition()
            self.assertTrue(imported[0].payload.Unpack(definition))
            self.assertEqual(definition.status, experience_pb2.QUARANTINED)
            self.assertFalse(definition.replay_allowed)
            experience.close()

    def test_trust_tamper_duplicate_validate_and_unmount(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            package = root / "portable.exp"
            signer = PackageSigner.generate()
            with Repository(root / "source") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=portable_definition(),
                )
                PackageService(source).export(
                    package,
                    name="portable",
                    version="1.0.0",
                    signer=signer,
                )
            experience = agent_experience(root / "target")
            experience.trust.add(signer.public_key_bytes)

            @experience.tool(capability="weather@1")
            def weather(city: str) -> str:
                return city

            mounted = experience.mount(package)
            self.assertEqual(mounted.trust, TrustStatus.SIGNED_TRUSTED)
            duplicate = experience.mount(package)
            self.assertEqual(duplicate.duplicate, 1)
            validated = experience.validate_mount("portable", lambda definition: True)
            self.assertEqual(validated.status, MountStatus.VALIDATED)
            unmounted = experience.unmount("portable")
            self.assertEqual(unmounted.status, MountStatus.UNMOUNTED)
            self.assertEqual(experience.mounts(), ())
            experience.close()

    def test_constructor_experiences_mount_after_tools_are_registered(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            package = root / "portable.exp"
            with Repository(root / "source") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=portable_definition(),
                )
                PackageService(source).export(package, name="portable", version="1.0.0")
            experience = agent_experience(root / "target", experiences=[package])

            @experience.tool(capability="weather@1")
            def weather(city: str) -> str:
                return city

            reports = experience.mounts()
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].compatible, 1)
            experience.close()

    def test_partial_compatibility_does_not_block_independent_experience(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            package = root / "mixed.exp"
            with Repository(root / "source") as source:
                for definition in (
                    portable_definition(),
                    portable_definition(
                        revision="revision-2",
                        content=b"search-content",
                        capability="capability://search@1",
                        experience_id="search-experience",
                    ),
                ):
                    source.append_event(
                        events_pb2.EXPERIENCE_ACTIVATED,
                        run_id="",
                        producer="test",
                        payload=definition,
                    )
                PackageService(source).export(package, name="mixed", version="1.0.0")
            experience = agent_experience(root / "target")

            @experience.tool(capability="weather@1")
            def weather(city: str) -> str:
                return city

            report = experience.mount(package)
            self.assertEqual(report.imported, 2)
            self.assertEqual(report.compatible, 1)
            self.assertEqual(report.incompatible, 1)
            self.assertEqual(report.needs_binding, 1)
            experience.close()

    def test_signature_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            package = root / "signed.exp"
            signer = PackageSigner.generate()
            with Repository(root / "source") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=portable_definition(),
                )
                PackageService(source).export(
                    package, name="signed", version="1.0.0", signer=signer
                )
            with zipfile.ZipFile(package) as archive:
                manifest = package_pb2.ExperiencePackageManifest.FromString(
                    archive.read("manifest.pb")
                )
                records = archive.read("records.bin")
            manifest.signature = bytes([manifest.signature[0] ^ 1]) + manifest.signature[1:]
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.pb", manifest.SerializeToString(deterministic=True))
                archive.writestr("records.bin", records)
            experience = agent_experience(root / "target")
            with self.assertRaisesRegex(ValueError, "signature"):
                experience.inspect_package(package)
            experience.close()

    def test_upgrade_rollback_unmount_and_secret_export_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            first = root / "first.exp"
            second = root / "second.exp"
            with Repository(root / "source-1") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=portable_definition(),
                )
                PackageService(source).export(first, name="upgradeable", version="1.0.0")
            with Repository(root / "source-2") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=portable_definition(
                        revision="revision-2", content=b"portable-content-v2"
                    ),
                )
                PackageService(source).export(second, name="upgradeable", version="1.1.0")
            experience = agent_experience(root / "target")

            @experience.tool(capability="weather@1")
            def weather(city: str) -> str:
                return city

            experience.mount(first)
            upgraded = experience.upgrade_mount("upgradeable", second)
            self.assertEqual(upgraded.package_version, "1.1.0")
            self.assertEqual(experience.mounts()[0].package_version, "1.1.0")
            rolled_back = experience.rollback_mount("upgradeable")
            self.assertEqual(rolled_back.package_version, "1.0.0")
            self.assertEqual(experience.mounts()[0].package_version, "1.0.0")
            experience.unmount("upgradeable")
            self.assertEqual(experience.mounts(), ())
            experience.close()

            with Repository(root / "secret-source") as source:
                secret = portable_definition(content=b"secret-content")
                secret.summary = "api_key=sk-this-must-never-be-exported"
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=secret,
                )
                with self.assertRaisesRegex(ValueError, "secret"):
                    PackageService(source).export(
                        root / "secret.exp", name="secret", version="1.0.0"
                    )

    def test_digest_pin_offline_and_custom_source(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            package = root / "portable.exp"
            with Repository(root / "source") as source:
                source.append_event(
                    events_pb2.EXPERIENCE_ACTIVATED,
                    run_id="",
                    producer="test",
                    payload=portable_definition(),
                )
                PackageService(source).export(package, name="portable", version="1.0.0")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            experience = agent_experience(root / "target")
            self.assertEqual(
                experience.inspect_package(package, sha256=digest).package_name, "portable"
            )
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                experience.inspect_package(package, sha256="0" * 64)
            experience.close()

            offline = agent_experience(root / "offline", mount_policy=MountPolicy(offline=True))
            with self.assertRaises(FileNotFoundError):
                offline.inspect_package("https://example.invalid/portable.exp", sha256=digest)
            offline.close()

            class FixedSource:
                def resolve(self, reference, *, policy, expected_sha256=""):  # type: ignore[no-untyped-def]
                    return ResolvedPackage(package, str(reference), digest)

            custom = agent_experience(root / "custom", package_source=FixedSource())

            @custom.tool(capability="weather@1")
            def weather(city: str) -> str:
                return city

            self.assertEqual(custom.mount("registry://portable").imported, 1)
            custom.close()


if __name__ == "__main__":
    unittest.main()
