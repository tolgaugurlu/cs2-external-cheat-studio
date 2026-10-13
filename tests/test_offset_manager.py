import ast
from datetime import datetime
import io
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import offset_manager as manager


def fixture(build=14190, source="sezzyaep", commit="b" * 40, typed=True,
            timestamp="2026-10-09T00:00:00+00:00"):
    info = {"build_number": build, "timestamp": timestamp}
    classes = {}
    for index, (cls, field) in enumerate(manager.REQUIRED_FIELDS):
        value = {"offset": 800 + index, "type": "int32"} if typed else 800 + index
        classes.setdefault(cls, {"fields": {}, "parent": None})["fields"][field] = value
    documents = {
        "info.json": info,
        "offsets.json": {"client.dll": {key: build * 100 + i for i, key in enumerate(manager.REQUIRED_GLOBALS)}},
        "client_dll.json": {"client.dll": {"classes": classes}},
        "buttons.json": {"client.dll": {"jump": 12345}},
    }
    files = {name: json.dumps(doc).encode() for name, doc in documents.items()}
    files["offsets.hpp"] = b"// Generated test fixture\n"
    repo = "a2x/cs2-dumper" if source == "a2x" else "sezzyaep/CS2-OFFSETS"
    head = dict(source=source, repository=repo, prefix="output/" if source == "a2x" else "",
                commit=commit, info=info, timestamp=datetime.fromisoformat(timestamp))
    return files, head


def archive(files, prefix=""):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, value in files.items():
            bundle.writestr("repo-sha/" + prefix + name, value)
        bundle.writestr("repo-sha/../../outside.json", "{}")
        bundle.writestr("repo-sha/run_me.py", "raise RuntimeError()")
    return buffer.getvalue()


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.files, self.head = fixture()

    def update(self, **kwargs):
        return manager.update_offsets(self.base, expected_build=14190, log=lambda _: None, **kwargs)

    def install(self):
        manager.install_files(self.base, self.files, self.head)

    def test_uses_patch_version_not_steam_client_version(self):
        self.assertEqual(manager.parse_patch_version("ClientVersion=2000930\nPatchVersion=1.41.9.0\n"), 14190)
        with self.assertRaises(manager.OffsetError):
            manager.parse_patch_version("ClientVersion=2000930\n")

    def test_both_schema_formats_and_inherited_fields(self):
        for typed in (False, True):
            files, head = fixture(typed=typed)
            data = manager.validate_files(files, head["source"], head["commit"])
            classes = data["classes"]
            classes["Child"] = {"fields": {}, "parent": "C_BaseEntity"}
            self.assertEqual(manager.field_offset(classes, "Child", "m_iHealth"), 800)
        with self.assertRaises(manager.OffsetError):
            manager.field_offset({"Cycle": {"parent": "Cycle"}}, "Cycle", "missing")

    def test_selects_matching_build_even_when_a2x_answers_first(self):
        _, old_head = fixture(14189, "a2x", "a" * 40, timestamp="2026-10-06T00:00:00+00:00")
        with patch.object(manager, "remote_head", side_effect=lambda source: old_head if source[0] == "a2x" else self.head), \
             patch.object(manager, "read_url", return_value=archive(self.files)) as download:
            snapshot = self.update()
        self.assertEqual(snapshot["source"], "sezzyaep")
        self.assertIn(self.head["commit"], download.call_args.args[0])
        self.assertEqual(manager.read_cache(self.base)["info"]["build_number"], 14190)
        self.assertFalse((self.base / "outside.json").exists())
        self.assertFalse((self.base / "output/run_me.py").exists())

    def test_remote_metadata_is_read_at_immutable_commit(self):
        replies = [json.dumps({"sha": self.head["commit"]}).encode(), self.files["info.json"]]
        with patch.object(manager, "read_url", side_effect=replies) as read:
            head = manager.remote_head(manager.SOURCES[1])
        self.assertEqual(head["commit"], self.head["commit"])
        self.assertIn("/" + head["commit"] + "/info.json", read.call_args.args[0])

    def test_offline_uses_complete_validated_cache(self):
        self.install()
        with patch.object(manager, "remote_head", side_effect=AssertionError("network used")):
            self.assertEqual(self.update(offline=True)["commit"], self.head["commit"])

    def test_network_outage_falls_back_to_cache(self):
        self.install()
        with patch.object(manager, "remote_head", side_effect=OSError("offline")):
            self.assertEqual(self.update()["commit"], self.head["commit"])

    def test_network_outage_without_verified_cache_fails(self):
        (self.base / "output").mkdir()
        (self.base / "output/offsets.json").write_bytes(self.files["offsets.json"])
        with patch.object(manager, "remote_head", side_effect=OSError("offline")):
            with self.assertRaises(manager.OffsetError):
                self.update()

    def test_corrupted_cache_is_rejected(self):
        self.install()
        (self.base / "output/client_dll.json").write_text("{}")
        with self.assertRaises(manager.OffsetError):
            self.update(offline=True)

    def test_mismatched_build_is_rejected_without_touching_cache(self):
        self.files, self.head = fixture(14189)
        self.install()
        before = (self.base / "output/info.json").read_bytes()
        with patch.object(manager, "remote_head", return_value=self.head):
            with self.assertRaises(manager.OffsetError):
                self.update()
        self.assertEqual((self.base / "output/info.json").read_bytes(), before)

    def test_partial_download_cannot_mix_with_cached_fields(self):
        self.install()
        newer_files, newer_head = fixture(commit="c" * 40, timestamp="2026-10-10T00:00:00+00:00")
        del newer_files["client_dll.json"]
        with patch.object(manager, "remote_head", return_value=newer_head), \
             patch.object(manager, "read_url", return_value=archive(newer_files)):
            self.assertEqual(self.update()["commit"], self.head["commit"])
        self.assertEqual(manager.read_cache(self.base)["commit"], self.head["commit"])

    def test_preserves_previous_generation(self):
        (self.base / "output").mkdir()
        (self.base / "output/old.json").write_text("old")
        backup = manager.install_files(self.base, self.files, self.head)
        self.assertEqual((backup / "old.json").read_text(), "old")
        self.assertFalse((self.base / "output/old.json").exists())

    def test_existing_latest_exports_are_synced_and_backed_up(self):
        self.install()
        (self.base / "offsets_latest.json").write_text("old data")
        manager.sync_legacy_exports(self.base)
        self.assertEqual((self.base / "offsets_latest.json").read_bytes(), self.files["offsets.json"])
        backups = list((self.base / "offset_backups").glob("offsets_latest.json.*.bak"))
        self.assertEqual(backups[0].read_text(), "old data")
        manager.sync_legacy_exports(self.base)
        self.assertEqual(len(list((self.base / "offset_backups").glob("*.bak"))), 1)

    def test_directory_swap_failure_restores_original(self):
        self.install()
        original_replace = manager.os.replace

        def fail_stage(source, destination):
            if Path(source).name.startswith(".offset-stage-"):
                raise PermissionError("simulated file lock")
            return original_replace(source, destination)

        with patch.object(manager.os, "replace", side_effect=fail_stage):
            with self.assertRaises(PermissionError):
                manager.install_files(self.base, *fixture(commit="c" * 40))
        self.assertEqual(manager.read_cache(self.base)["commit"], self.head["commit"])

    def test_older_online_snapshot_does_not_downgrade_cache(self):
        self.install()
        _, older = fixture(commit="a" * 40, timestamp="2026-10-08T00:00:00+00:00")
        with patch.object(manager, "remote_head", return_value=older), \
             patch.object(manager, "download_files", side_effect=AssertionError("downgrade")):
            self.assertEqual(self.update()["commit"], self.head["commit"])

    def test_malformed_manifest_is_rejected(self):
        (self.base / "output").mkdir()
        (self.base / "output" / manager.MANIFEST).write_text("[]")
        with self.assertRaises(manager.OffsetError):
            self.update(offline=True)

    def test_archive_info_must_match_queried_commit(self):
        wrong_files, _ = fixture(14189)
        with patch.object(manager, "read_url", return_value=archive(wrong_files)):
            with self.assertRaises(manager.OffsetError):
                manager.download_files(self.head)


class EngineIntegrationTests(unittest.TestCase):
    """Exercise the real engine methods without importing WinAPI/UI workers."""

    def engine_class(self, updater):
        path = Path(__file__).resolve().parents[1] / "memory_bot.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CS2Engine")
        namespace = {"update_offsets": updater, "field_offset": manager.field_offset,
                     "_BASE_DIR": str(path.parent), "print": lambda *args: None,
                     "logging":logging,"OffsetError":manager.OffsetError}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
        return namespace["CS2Engine"]

    def test_engine_accepts_typed_snapshot_and_updated_fields(self):
        files, head = fixture()
        snapshot = manager.validate_files(files, head["source"], head["commit"])
        engine_cls = self.engine_class(lambda *a, **kw: snapshot)
        engine = object.__new__(engine_cls)
        self.assertTrue(engine.fetch())
        self.assertTrue(engine.ready)
        self.assertEqual(engine._off_id, 808)
        with self.assertRaises(manager.OffsetError):
            engine._f("C_CSPlayerPawn", "missing")

    def test_failed_update_leaves_engine_inactive(self):
        def fail(*args, **kwargs):
            raise manager.OffsetError("build mismatch")
        engine_cls = self.engine_class(fail)
        engine = object.__new__(engine_cls)
        self.assertFalse(engine.fetch())
        self.assertFalse(engine.ready)
        self.assertEqual(engine.off, {})
        self.assertIn("build mismatch", engine.offset_status)

    def test_ready_from_verified_cache_without_network_lookup(self):
        files, head = fixture()
        snapshot = manager.validate_files(files, head['source'], head['commit'])
        calls=[]
        def updater(*args,**kwargs):
            calls.append(kwargs.get('offline',False))
            if not kwargs.get('offline'): raise AssertionError('Unexpected network lookup')
            return snapshot
        engine=object.__new__(self.engine_class(updater))
        self.assertTrue(engine.fetch())
        self.assertEqual(calls,[True])
        self.assertFalse(engine.loading)

    def test_missing_cache_falls_back_to_online_validation(self):
        files, head = fixture()
        snapshot = manager.validate_files(files, head['source'], head['commit'])
        calls=[]
        def updater(*args,**kwargs):
            calls.append(kwargs.get('offline',False))
            if kwargs.get('offline'): raise manager.OffsetError('No matching cache')
            return snapshot
        engine=object.__new__(self.engine_class(updater))
        self.assertTrue(engine.fetch())
        self.assertEqual(calls,[True,False])

    def test_entity_lookup_uses_live_verified_entry_size(self):
        engine_cls = self.engine_class(None)
        engine = object.__new__(engine_cls)
        entity_list, chunk, pawn = 0x10000, 0x20000, 0x30000
        memory = {entity_list + 0x10: chunk, chunk + 112 * 7: pawn,
                  chunk + 120 * 7: 0}
        engine.read_longlong = lambda address: memory.get(address, 0)
        self.assertEqual(engine.entity_from_index(entity_list, 7), pawn)

    def test_entity_handle_preserves_chunk_boundary_and_discards_serial(self):
        engine_cls = self.engine_class(None)
        engine = object.__new__(engine_cls)
        entity_list, chunk = 0x10000, 0x20000
        memory = {entity_list + 0x10 + 8: chunk, chunk + 112 * 3: 0x30000}
        engine.read_longlong = lambda address: memory.get(address, 0)
        handle = (77 << 15) | 515
        self.assertEqual(engine.entity_from_index(entity_list, handle), 0x30000)

    def test_empty_chunks_and_invalid_handles_do_not_read_entities(self):
        engine_cls = self.engine_class(None)
        engine = object.__new__(engine_cls)
        reads = []
        engine.read_longlong = lambda address: reads.append(address) or 0
        for index in (0, -1, 0xFFFFFFFF):
            self.assertEqual(engine.entity_from_index(0x10000, index), 0)
        self.assertEqual(engine.entity_from_index(0, 7), 0)
        self.assertEqual(reads, [])
        self.assertEqual(engine.entity_from_index(0x10000, 7), 0)
        self.assertEqual(reads, [0x10010])


if __name__ == "__main__":
    unittest.main()
