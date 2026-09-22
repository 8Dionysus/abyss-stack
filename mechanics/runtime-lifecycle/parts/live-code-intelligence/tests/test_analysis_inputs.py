from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PART_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PART_ROOT))

import analysis_inputs  # noqa: E402
from analysis_inputs import AnalysisInputError, CaptureLimits, capture_tree, seal_tree  # noqa: E402


class AnalysisInputCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        self.source.mkdir()

    def write(self, path: str, content: bytes, *, root: Path | None = None) -> Path:
        target = (self.source if root is None else root) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_capture_preserves_bytes_and_does_not_reopen_the_working_tree(self) -> None:
        content = 'message = "🜁 привет"\r\n'.encode("utf-8")
        path = self.write("package/source.py", content)
        self.write("empty.py", b"")
        captured = capture_tree(self.source, require_utf8=True)
        self.assertEqual(captured.sources, {"empty.py": b"", "package/source.py": content})
        self.assertEqual(captured.directories, ("package",))
        self.assertEqual(captured.files[1].sha256, hashlib.sha256(content).hexdigest())
        path.write_bytes(b"changed\n")
        captured.sources.clear()
        identity = captured.identity()
        identity["files"].clear()
        identity["directories"].clear()
        self.assertEqual(captured.sources["package/source.py"], content)
        self.assertEqual(len(captured.identity()["files"]), 2)
        self.assertEqual(captured.directories, ("package",))
        with self.assertRaises(FrozenInstanceError):
            captured.files[0].content = b"replacement"

    def test_identity_is_content_addressed_portable_and_order_independent(self) -> None:
        other = self.base / "other"
        other.mkdir()
        entries = [("a.py", b"a\r\n"), ("package/z.py", b"z\n"), ("empty.py", b"")]
        for path, content in entries:
            self.write(path, content)
        for path, content in reversed(entries):
            self.write(path, content, root=other)
        first = capture_tree(self.source)
        second = capture_tree(other)
        self.assertNotEqual(first.root, second.root)
        self.assertEqual(first.digest, second.digest)
        os.utime(other / "a.py", (1, 1))
        (other / "a.py").chmod(0o600)
        self.assertEqual(first.digest, capture_tree(other).digest)
        self.write("a.py", b"a\n", root=other)
        self.assertNotEqual(first.digest, capture_tree(other).digest)

    def test_selection_is_explicit_and_bound_even_when_selected_bytes_match(self) -> None:
        self.write("a.py", b"a")
        complete = capture_tree(self.source)
        selected = capture_tree(self.source, suffixes=(".py",))
        excluded = capture_tree(self.source, excluded_names=(".git",))
        self.assertEqual(complete.sources, selected.sources)
        self.assertEqual(complete.sources, excluded.sources)
        self.assertEqual(len({complete.digest, selected.digest, excluded.digest}), 3)
        self.assertEqual(selected.identity()["coverage"], "declared_input_view_only")
        self.write("a.txt", b"not source")
        self.write(".git/ignored.py", b"ignored")
        self.assertEqual(capture_tree(self.source, suffixes=(".py",),
                                      excluded_names=(".git",)).sources, {"a.py": b"a"})
        self.assertEqual(capture_tree(self.source, suffixes=(".pyi", ".py", ".py"),
                                      excluded_names=(".git", ".git")).digest,
                         capture_tree(self.source, suffixes=(".py", ".pyi"),
                                      excluded_names=(".git",)).digest)

    def test_complete_dependency_view_includes_metadata_data_and_empty_directories(self) -> None:
        entries = {"lib/pkg/__init__.py": b"", "lib/pkg/data.bin": b"\x00\xff",
                   "lib/pkg-1.0.dist-info/METADATA": b"Name: pkg\nVersion: 1.0\n",
                   "environment.json": b"[]\n", ".git/config": b"no implicit ignores"}
        for path, content in entries.items():
            self.write(path, content)
        captured = capture_tree(self.source)
        self.assertEqual(captured.sources, entries)
        (self.source / "stubs").mkdir()
        self.assertNotEqual(captured.digest, capture_tree(self.source).digest)
        self.assertIn("stubs", capture_tree(self.source).directories)
        empty = self.base / "empty-resolver"
        empty.mkdir()
        self.assertEqual(capture_tree(empty).sources, {})
        with self.assertRaises(AnalysisInputError):
            capture_tree(self.base / "unknown-resolver")

    def test_utf8_validation_is_explicit_and_never_replaces_bad_bytes(self) -> None:
        self.write("a.py", b"\xff\r\n")
        self.assertEqual(capture_tree(self.source).sources["a.py"], b"\xff\r\n")
        with self.assertRaises(AnalysisInputError):
            capture_tree(self.source, require_utf8=True)

    def test_symlinks_at_root_ancestor_and_included_entries_are_rejected(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret.py").write_bytes(b"outside")
        root_link = self.base / "root-link"
        root_link.symlink_to(self.source, target_is_directory=True)
        ancestor = self.base / "ancestor"
        ancestor.symlink_to(self.base, target_is_directory=True)
        for root in (root_link, ancestor / "source"):
            with self.subTest(root=root), self.assertRaises(AnalysisInputError):
                capture_tree(root)
        for name, target in (("file.py", outside / "secret.py"), ("directory", outside),
                             ("unselected.txt", outside / "secret.py")):
            link = self.source / name
            link.symlink_to(target)
            with self.subTest(name=name), self.assertRaises(AnalysisInputError):
                capture_tree(self.source, suffixes=(".py",))
            link.unlink()
        (self.source / ".venv").symlink_to(outside, target_is_directory=True)
        self.assertEqual(capture_tree(self.source, excluded_names=(".venv",)).sources, {})

    def test_special_files_are_rejected_without_blocking(self) -> None:
        os.mkfifo(self.source / "fifo")
        with self.assertRaisesRegex(AnalysisInputError, "special file"):
            capture_tree(self.source)

    def test_noncanonical_names_and_parent_traversal_are_rejected(self) -> None:
        for name in ("bad\\name.py", "bad:name.py", "bad\udcff.py"):
            target = self.source / name
            target.write_bytes(b"")
            with self.subTest(name=name), self.assertRaises(AnalysisInputError):
                capture_tree(self.source)
            target.unlink()
        for root in ("relative", self.source / ".." / "source"):
            with self.subTest(root=root), self.assertRaises(AnalysisInputError):
                capture_tree(root)

    def test_invalid_configuration_is_rejected(self) -> None:
        for kwargs in ({"suffixes": []}, {"suffixes": ()}, {"suffixes": ("py",)},
                       {"suffixes": (".",)}, {"suffixes": (".py/else",)},
                       {"excluded_names": [".git"]}, {"excluded_names": ("..",)},
                       {"limits": {}}, {"require_utf8": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(AnalysisInputError):
                capture_tree(self.source, **kwargs)
        for kwargs in ({"max_files": True}, {"max_entries": 0}, {"max_depth": -1},
                       {"max_file_bytes": 1.5}, {"max_total_bytes": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(AnalysisInputError):
                CaptureLimits(**kwargs)
        with self.assertRaises(AnalysisInputError):
            capture_tree(None)

    def test_file_entry_depth_and_byte_bounds_are_enforced(self) -> None:
        self.write("a.py", b"1234")
        self.write("b.py", b"5678")
        (self.source / "dir" / "deep").mkdir(parents=True)
        for limits, message in (
            (replace(CaptureLimits(), max_files=1), "file count"),
            (replace(CaptureLimits(), max_entries=1), "entry count"),
            (replace(CaptureLimits(), max_depth=1), "depth"),
            (replace(CaptureLimits(), max_file_bytes=3), "size"),
            (replace(CaptureLimits(), max_file_bytes=4, max_total_bytes=7), "total bytes"),
        ):
            with self.subTest(limits=limits), self.assertRaisesRegex(AnalysisInputError, message):
                capture_tree(self.source, limits=limits)
        exact = replace(CaptureLimits(), max_files=2, max_entries=4, max_depth=2,
                        max_file_bytes=4, max_total_bytes=8)
        self.assertEqual(len(capture_tree(self.source, limits=exact).files), 2)
        with self.assertRaisesRegex(AnalysisInputError, "entry count"):
            capture_tree(self.source, excluded_names=("a.py", "b.py", "dir"),
                         limits=replace(CaptureLimits(), max_entries=2))

    def test_file_replaced_by_symlink_during_open_is_rejected(self) -> None:
        target = self.write("a.py", b"safe")
        outside = self.base / "outside.py"
        outside.write_bytes(b"outside")
        original = os.open

        def change_on_open(path, flags, *args, **kwargs):
            if path == "a.py":
                target.unlink()
                target.symlink_to(outside)
            return original(path, flags, *args, **kwargs)

        with mock.patch.object(analysis_inputs.os, "open", side_effect=change_on_open):
            with self.assertRaises(AnalysisInputError):
                capture_tree(self.source)

    def test_file_mutation_during_read_is_rejected(self) -> None:
        target = self.write("a.py", b"before")
        original = os.read
        changed = False

        def change_on_read(descriptor, count):
            nonlocal changed
            content = original(descriptor, count)
            if content and not changed:
                target.write_bytes(b"after!")
                changed = True
            return content

        with mock.patch.object(analysis_inputs.os, "read", side_effect=change_on_read):
            with self.assertRaisesRegex(AnalysisInputError, "changed while reading"):
                capture_tree(self.source)

    def test_directory_mutation_during_scan_is_rejected(self) -> None:
        self.write("a.py", b"before")
        original = os.read

        def add_on_read(descriptor, count):
            content = original(descriptor, count)
            if content:
                self.write("added.py", b"after")
            return content

        with mock.patch.object(analysis_inputs.os, "read", side_effect=add_on_read):
            with self.assertRaisesRegex(AnalysisInputError, "directory changed"):
                capture_tree(self.source)

    def test_mutation_between_passes_is_rejected(self) -> None:
        target = self.write("a.py", b"before")
        original = analysis_inputs._capture_pass

        def change_after_pass(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs["keep_bytes"]:
                target.write_bytes(b"after!")
            return result

        with mock.patch.object(analysis_inputs, "_capture_pass", side_effect=change_after_pass):
            with self.assertRaisesRegex(AnalysisInputError, "between complete reads"):
                capture_tree(self.source)

    def test_root_replacement_before_return_is_rejected(self) -> None:
        self.write("a.py", b"before")
        original = analysis_inputs._capture_pass

        def replace_root(*args, **kwargs):
            result = original(*args, **kwargs)
            if not kwargs["keep_bytes"]:
                self.source.rename(self.base / "old-root")
                self.source.mkdir()
                self.write("a.py", b"before")
            return result

        with mock.patch.object(analysis_inputs, "_capture_pass", side_effect=replace_root):
            with self.assertRaisesRegex(AnalysisInputError, "root changed"):
                capture_tree(self.source)

    def test_sealed_tree_exposes_only_captured_bytes_and_closes_descriptors(self) -> None:
        target = self.write("package/a.py", b"captured\r\n")
        self.write("empty.py", b"")
        (self.source / "stubs").mkdir()
        captured = capture_tree(self.source)
        target.write_bytes(b"subsequent host drift")
        with seal_tree(captured, namespace_root="/analysis/source") as sealed:
            self.assertEqual(sealed.digest, captured.digest)
            self.assertEqual(sealed.arguments[:6],
                             ("--dir", "/analysis/source", "--dir", "/analysis/source/package",
                              "--dir", "/analysis/source/stubs"))
            self.assertEqual(len(sealed.pass_fds), 2)
            for descriptor, item in zip(sealed.pass_fds, captured.files):
                self.assertEqual(os.read(descriptor, 1024), item.content)
                with self.assertRaises(OSError):
                    os.write(descriptor, b"tamper")
                with self.assertRaises(OSError):
                    os.ftruncate(descriptor, 1)
        for descriptor in sealed.pass_fds:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_sealing_rejects_manifest_tampering_and_namespace_traversal(self) -> None:
        self.write("a.py", b"captured")
        captured = capture_tree(self.source)
        for changed in (replace(captured, digest="0" * 64),
                        replace(captured, directories=("missing/parent",)),
                        replace(captured, files=(replace(captured.files[0], path="../escape"),)),
                        replace(captured, files=(replace(captured.files[0], content=b"tamper"),))):
            with self.subTest(changed=changed), self.assertRaises(AnalysisInputError):
                with seal_tree(changed, namespace_root="/analysis/source"):
                    self.fail("tampered capture was staged")
        for root in ("relative", "/", "/../escape", "/analysis//source", "/analysis/source/"):
            with self.subTest(root=root), self.assertRaises(AnalysisInputError):
                with seal_tree(captured, namespace_root=root):
                    self.fail("invalid namespace root was accepted")

    def test_partial_staging_failure_closes_allocated_descriptors(self) -> None:
        self.write("a.py", b"a")
        self.write("b.py", b"b")
        captured = capture_tree(self.source)
        original = os.memfd_create
        opened = []

        def fail_second(*args, **kwargs):
            if opened:
                raise OSError("descriptor budget exhausted")
            descriptor = original(*args, **kwargs)
            opened.append(descriptor)
            return descriptor

        with mock.patch.object(analysis_inputs.os, "memfd_create", side_effect=fail_second):
            with self.assertRaises(AnalysisInputError):
                with seal_tree(captured, namespace_root="/analysis/source"):
                    self.fail("partial input tree escaped")
        self.assertEqual(len(opened), 1)
        with self.assertRaises(OSError):
            os.fstat(opened[0])

    def test_sealing_handles_short_writes_without_losing_input_bytes(self) -> None:
        self.write("a.py", b"capture more than one short write")
        captured = capture_tree(self.source)
        original = os.write
        with mock.patch.object(analysis_inputs.os, "write",
                               side_effect=lambda fd, data: original(fd, data[:3])):
            with seal_tree(captured, namespace_root="/analysis/source") as sealed:
                self.assertEqual(os.read(sealed.pass_fds[0], 1024), captured.files[0].content)

    def test_caller_failure_is_not_relabelled_as_staging_failure(self) -> None:
        self.write("a.py", b"captured")
        failure = OSError("provider launch failed")
        with self.assertRaises(OSError) as raised:
            with seal_tree(capture_tree(self.source), namespace_root="/analysis/source") as sealed:
                raise failure
        self.assertIs(raised.exception, failure)
        with self.assertRaises(OSError):
            os.fstat(sealed.pass_fds[0])


if __name__ == "__main__":
    unittest.main()
