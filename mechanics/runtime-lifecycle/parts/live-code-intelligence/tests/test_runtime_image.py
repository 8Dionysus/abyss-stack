from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_image as runtime  # noqa: E402


def file_entry(path: str, content: bytes, mode: int = 0o644) -> dict:
    return {"path": path, "kind": "file", "mode": mode, "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}


class RuntimeImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "runtime"
        self.root.mkdir()
        (self.root / "bin").mkdir(mode=0o755)
        (self.root / "package").mkdir(mode=0o755)
        self.contents = {"package/main.js": b'console.log("immutable");\n', "bin/node": b"ELF fixture\x00\xff"}
        for path, content in self.contents.items():
            (self.root / path).write_bytes(content)
            (self.root / path).chmod(0o755 if path == "bin/node" else 0o644)
        (self.root / "bin/indexer").symlink_to("../package/main.js")
        self.expected = {"schema": runtime.SCHEMA, "entries": [
            {"path": "bin", "kind": "directory", "mode": 0o755},
            {"path": "package", "kind": "directory", "mode": 0o755},
            {"path": "bin/indexer", "kind": "symlink", "mode": 0o777, "target": "../package/main.js"},
            file_entry("package/main.js", self.contents["package/main.js"]),
            file_entry("bin/node", self.contents["bin/node"], 0o755),
        ]}

    def capture(self):
        return runtime.capture_runtime_tree(self.root, expected=self.expected)

    def test_exact_bytes_modes_layout_links_and_fresh_manifest(self) -> None:
        captured = self.capture()
        self.assertEqual(dict(captured.files), self.contents)
        self.assertEqual(captured.manifest()["entries"], sorted(self.expected["entries"], key=lambda row: row["path"]))
        captured.manifest()["entries"].clear()
        self.expected["entries"].clear()
        self.assertEqual(len(captured.manifest()["entries"]), 5)
        self.assertEqual(captured.digest, hashlib.sha256(captured.manifest_bytes).hexdigest())

    def test_manifest_is_order_independent_but_mode_sensitive(self) -> None:
        first = self.capture()
        self.expected["entries"].reverse()
        self.assertEqual(first.digest, self.capture().digest)
        row = next(item for item in self.expected["entries"] if item["path"] == "bin/node")
        row["mode"] = 0o644
        (self.root / "bin/node").chmod(0o644)
        self.assertNotEqual(first.digest, self.capture().digest)

    def test_unknown_missing_extra_paths_and_empty_directories_fail(self) -> None:
        for relative in ("foreign", "empty"):
            path = self.root / relative
            path.mkdir() if relative == "empty" else path.write_bytes(b"unknown")
            with self.subTest(path=path), self.assertRaisesRegex(runtime.RuntimeImageError, "path set"):
                self.capture()
            path.rmdir() if relative == "empty" else path.unlink()
        (self.root / "package/main.js").unlink()
        with self.assertRaisesRegex(runtime.RuntimeImageError, "path set"):
            self.capture()

    def test_wrong_bytes_size_mode_and_link_target_fail(self) -> None:
        original = deepcopy(self.expected)
        for field, value in (("bytes", 0), ("sha256", "0" * 64), ("mode", 0o644)):
            self.expected = deepcopy(original)
            next(row for row in self.expected["entries"] if row["path"] == "bin/node")[field] = value
            with self.subTest(field=field), self.assertRaises(runtime.RuntimeImageError):
                self.capture()
        self.expected = original
        (self.root / "bin/indexer").unlink()
        (self.root / "bin/indexer").symlink_to("node")
        with self.assertRaisesRegex(runtime.RuntimeImageError, "link target"):
            self.capture()

    def test_manifest_shape_paths_modes_digests_and_link_grammar_fail_closed(self) -> None:
        original = deepcopy(self.expected)
        bad_rows = [
            {"extra": True}, {"path": "../escape"}, {"path": "/absolute"}, {"path": "bin//node"},
            {"path": "bin/./node"}, {"path": "bin\\node"}, {"path": "bad\udcff"},
            {"kind": "device"}, {"kind": []}, {"mode": 0o4755}, {"mode": True},
            {"bytes": True}, {"bytes": -1}, {"sha256": "0" * 63}, {"sha256": "A" * 64},
        ]
        for change in bad_rows:
            self.expected = deepcopy(original)
            self.expected["entries"][-1].update(change)
            with self.subTest(change=change), self.assertRaises(runtime.RuntimeImageError):
                self.capture()
        for target in ("/etc/passwd", "../../escape", "missing", "../package", "indexer",
                       "../package/../bin/node", "./node", "node/", "bad\x00", "../bad\udcff"):
            self.expected = deepcopy(original)
            self.expected["entries"][2]["target"] = target
            with self.subTest(target=target), self.assertRaises(runtime.RuntimeImageError):
                self.capture()
        self.expected = deepcopy(original)
        self.expected["entries"].append(deepcopy(self.expected["entries"][-1]))
        with self.assertRaisesRegex(runtime.RuntimeImageError, "duplicate"):
            self.capture()
        self.expected = deepcopy(original)
        self.expected["entries"].pop(0)
        with self.assertRaisesRegex(runtime.RuntimeImageError, "parent"):
            self.capture()

    def test_no_symlinked_root_ancestor_directory_file_or_special_inputs(self) -> None:
        alias = self.base / "alias"
        alias.symlink_to(self.root)
        for root in (alias, alias / "package", "relative", self.root / ".." / "runtime", None):
            with self.subTest(root=root), self.assertRaises(runtime.RuntimeImageError):
                runtime.capture_runtime_tree(root, expected=self.expected)
        node = self.root / "bin/node"
        node.unlink()
        node.symlink_to("../package/main.js")
        with self.assertRaisesRegex(runtime.RuntimeImageError, "type, mode"):
            self.capture()
        node.unlink()
        os.mkfifo(node)
        with self.assertRaisesRegex(runtime.RuntimeImageError, "special file"):
            self.capture()
        node.unlink()
        os.link(self.root / "package/main.js", node)
        with self.assertRaisesRegex(runtime.RuntimeImageError, "hard link"):
            self.capture()

    def test_limits_bound_manifest_and_actual_tree(self) -> None:
        for limits in (runtime.RuntimeLimits(max_entries=4), runtime.RuntimeLimits(max_depth=1),
                       runtime.RuntimeLimits(max_file_bytes=2),
                       runtime.RuntimeLimits(max_file_bytes=30, max_total_bytes=31)):
            with self.subTest(limits=limits), self.assertRaises(runtime.RuntimeImageError):
                runtime.capture_runtime_tree(self.root, expected=self.expected, limits=limits)
        for arguments in ({"max_entries": True}, {"max_depth": 0}, {"max_total_bytes": 1}):
            with self.subTest(arguments=arguments), self.assertRaises(runtime.RuntimeImageError):
                runtime.RuntimeLimits(**arguments)
        with self.assertRaises(runtime.RuntimeImageError):
            runtime.capture_runtime_tree(self.root, expected=self.expected, limits={})
        for index in range(5):
            (self.root / str(index)).write_bytes(b"")
        with self.assertRaisesRegex(runtime.RuntimeImageError, "entry count"):
            runtime.capture_runtime_tree(self.root, expected=self.expected, limits=runtime.RuntimeLimits(max_entries=6))

    def test_mutation_during_read_or_between_layout_scans_is_rejected(self) -> None:
        original = runtime.os.read
        changed = False

        def drift(fd, count):
            nonlocal changed
            chunk = original(fd, count)
            if chunk and not changed:
                changed = True
                (self.root / "bin/node").write_bytes(b"drift")
            return chunk

        with mock.patch.object(runtime.os, "read", side_effect=drift):
            with self.assertRaises(runtime.RuntimeImageError):
                self.capture()
        (self.root / "bin/node").write_bytes(self.contents["bin/node"])
        scan = runtime._scan
        calls = 0

        def add_before_second(fd, limits):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.root / "extra").write_bytes(b"late")
            return scan(fd, limits)

        with mock.patch.object(runtime, "_scan", side_effect=add_before_second):
            with self.assertRaisesRegex(runtime.RuntimeImageError, "changed during capture"):
                self.capture()

    def test_replaced_root_and_file_to_link_races_are_rejected(self) -> None:
        scan = runtime._scan
        calls = 0

        def replace_root(fd, limits):
            nonlocal calls
            result = scan(fd, limits)
            calls += 1
            if calls == 2:
                self.root.rename(self.base / "old")
                self.root.mkdir()
            return result

        with mock.patch.object(runtime, "_scan", side_effect=replace_root):
            with self.assertRaisesRegex(runtime.RuntimeImageError, "changed during capture"):
                self.capture()
        self.root.rmdir()
        (self.base / "old").rename(self.root)
        read = runtime._read_file

        def substitute(fd, item, signature):
            node = self.root / item["path"]
            node.unlink()
            node.symlink_to(self.base / "outside")
            return read(fd, item, signature)

        (self.base / "outside").write_bytes(b"not admitted")
        with mock.patch.object(runtime, "_read_file", side_effect=substitute):
            with self.assertRaises(runtime.RuntimeImageError):
                self.capture()

    def test_sealed_bytes_modes_links_and_lifetime_ignore_later_host_changes(self) -> None:
        captured = self.capture()
        (self.root / "bin/node").write_bytes(b"different")
        (self.root / "package/main.js").unlink()
        with runtime.seal_runtime_tree(captured, namespace_root="/provider") as sealed:
            self.assertEqual(len(sealed.pass_fds), 2)
            self.assertNotIn(str(self.root), sealed.arguments)
            self.assertNotIn("--ro-bind", sealed.arguments)
            self.assertIn("--symlink", sealed.arguments)
            self.assertEqual(sealed.arguments[-3:], ("--symlink", "../package/main.js", "/provider/bin/indexer"))
            for (path, content), fd in zip(captured.files, sealed.pass_fds, strict=True):
                self.assertEqual(os.read(fd, len(content) + 1), content)
                self.assertEqual(stat.S_IMODE(os.fstat(fd).st_mode), 0o755 if path == "bin/node" else 0o644)
                self.assertEqual(fcntl.fcntl(fd, fcntl.F_GET_SEALS),
                                 fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
                with self.assertRaises(OSError):
                    os.write(fd, b"mutation")
            fds = sealed.pass_fds
        for fd in fds:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_tampered_captures_and_bad_namespace_are_rejected_before_allocation(self) -> None:
        image = self.capture()
        for value in (replace(image, digest="0" * 64), replace(image, manifest_bytes=b"{}"),
                      replace(image, files=()), replace(image, files=(("bin/node", b"changed"), *image.files[1:]))):
            with self.subTest(value=value), mock.patch.object(runtime.os, "memfd_create") as allocate:
                with self.assertRaises(runtime.RuntimeImageError):
                    with runtime.seal_runtime_tree(value, namespace_root="/provider"):
                        pass
                allocate.assert_not_called()
        for root in ("/", "relative", "/a/../b", "/a//b", "/a/", None):
            with self.subTest(root=root), self.assertRaises(runtime.RuntimeImageError):
                with runtime.seal_runtime_tree(image, namespace_root=root):
                    pass

    def test_partial_writes_and_failed_allocation_close_every_owned_descriptor(self) -> None:
        image = self.capture()
        write = runtime.os.write
        with mock.patch.object(runtime.os, "write", side_effect=lambda fd, data: write(fd, data[:2])):
            with runtime.seal_runtime_tree(image, namespace_root="/provider") as sealed:
                for (_, content), fd in zip(image.files, sealed.pass_fds, strict=True):
                    self.assertEqual(os.read(fd, 100), content)
        allocate = runtime.os.memfd_create
        fds = []

        def fail_second(*args, **kwargs):
            if fds:
                raise OSError("descriptor budget exhausted")
            fds.append(allocate(*args, **kwargs))
            return fds[-1]

        with mock.patch.object(runtime.os, "memfd_create", side_effect=fail_second):
            with self.assertRaises(runtime.RuntimeImageError):
                with runtime.seal_runtime_tree(image, namespace_root="/provider"):
                    pass
        for fd in fds:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_zero_write_and_caller_exception_release_staged_descriptors(self) -> None:
        image = self.capture()
        with mock.patch.object(runtime.os, "write", return_value=0):
            with self.assertRaisesRegex(runtime.RuntimeImageError, "complete runtime bytes"):
                with runtime.seal_runtime_tree(image, namespace_root="/provider"):
                    pass
        fds = ()
        with self.assertRaisesRegex(RuntimeError, "caller"):
            with runtime.seal_runtime_tree(image, namespace_root="/provider") as sealed:
                fds = sealed.pass_fds
                raise RuntimeError("caller")
        for fd in fds:
            with self.assertRaises(OSError):
                os.fstat(fd)


if __name__ == "__main__":
    unittest.main()
