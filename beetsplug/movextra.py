"""Move the remaining contents of an imported release into the music library."""

from __future__ import annotations

import filecmp
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from beets import config, util
from beets.plugins import BeetsPlugin
from beets.util import MoveOperation

if TYPE_CHECKING:
    from typing import Any

    from beets.importer import ImportSession, ImportTask
    from beets.library import Item, Library

DuplicateAction = Literal["merge", "skip", "keep", "remove"]

OPERATION_LABELS: dict[MoveOperation, str] = {
    MoveOperation.MOVE: "Moving",
    MoveOperation.COPY: "Copying",
    MoveOperation.LINK: "Linking",
    MoveOperation.HARDLINK: "Hardlinking",
    MoveOperation.REFLINK: "Reflinking",
    MoveOperation.REFLINK_AUTO: "Reflinking",
}


@dataclass(frozen=True)
class MoveJob:
    """A completed import task whose leftovers still need to be moved."""

    toppath: Path | None
    source_items: tuple[Path, ...]
    destination_items: tuple[Path, ...]
    operation: MoveOperation
    delete_source: bool
    is_reimport: bool


@dataclass(frozen=True)
class ItemMove:
    """A file operation beets performed outside of an import."""

    album_id: int | None
    source: Path
    destination: Path
    operation: MoveOperation


def _to_path(path: Any) -> Path:
    """Convert a beets path into a normalized absolute ``Path``."""
    return Path(os.path.normpath(os.path.abspath(os.fsdecode(path))))


def _common_parent(paths: tuple[Path, ...]) -> Path | None:
    """Return the common parent directory of a set of files."""
    parents = {path.parent for path in paths}
    if not parents:
        return None
    if len(parents) == 1:
        return next(iter(parents))

    return Path(os.path.commonpath([str(parent) for parent in parents]))


class MovextraPlugin(BeetsPlugin):
    """Move non-imported release files alongside the imported music."""

    def __init__(self) -> None:
        super().__init__()

        self.config.add(
            {
                "duplicate_action": "merge",
            }
        )

        self._lock = threading.Lock()
        self._jobs: list[MoveJob] = []
        self._item_moves: list[ItemMove] = []
        self._import_active = False
        self._imported_paths: set[Path] = set()
        self._task_sources: dict[int, tuple[Path, ...]] = {}
        self._toppath_roots: dict[Path, set[Path]] = {}

        self.register_listener("import_begin", self._on_import_begin)
        self.register_listener("import_task_created", self._on_task_created)
        self.register_listener("import_task_files", self._on_task_files)
        self.register_listener("item_moved", self._on_item_moved)
        self.register_listener("item_copied", self._on_item_copied)
        self.register_listener("item_linked", self._on_item_linked)
        self.register_listener("item_hardlinked", self._on_item_hardlinked)
        self.register_listener("item_reflinked", self._on_item_reflinked)
        self.register_listener("cli_exit", self._on_cli_exit)

    def _on_import_begin(self, session: ImportSession) -> None:
        """Reset state at the start of an import session."""
        del session
        with self._lock:
            self._import_active = True
            self._jobs.clear()
            self._item_moves.clear()
            self._imported_paths.clear()
            self._task_sources.clear()
            self._toppath_roots.clear()

    def _on_task_created(self, session: ImportSession, task: ImportTask) -> None:
        """Record the original source paths before other plugins can alter them."""
        del session
        source_items = tuple(_to_path(item.path) for item in task.items)
        toppath = _to_path(task.toppath) if task.toppath is not None else None
        base_root = _common_parent(source_items)

        with self._lock:
            self._task_sources[id(task)] = source_items
            self._imported_paths.update(source_items)
            if toppath is not None and base_root is not None:
                self._toppath_roots.setdefault(toppath, set()).add(base_root)

    def _on_task_files(self, session: ImportSession, task: ImportTask) -> None:
        """Queue a task after beets has handled its audio files."""
        if task.toppath is None:
            self._log.debug("Skipping query-based import task.")
            return

        operation = self._operation(session)
        if operation is None:
            self._log.debug(
                "No import file operation is configured; not moving extras."
            )
            return

        destination_items = tuple(_to_path(item.path) for item in task.imported_items())
        if not destination_items:
            return

        with self._lock:
            source_items = self._task_sources.get(id(task))

        if not source_items:
            self._log.warning(
                "Could not determine source paths for task; not moving extras."
            )
            return

        delete_source = operation is MoveOperation.COPY and session.config[
            "delete"
        ].get(bool)

        with self._lock:
            self._jobs.append(
                MoveJob(
                    toppath=_to_path(task.toppath),
                    source_items=source_items,
                    destination_items=destination_items,
                    operation=operation,
                    delete_source=delete_source,
                    is_reimport=self._is_reimport(session),
                )
            )

    def _operation(self, session: ImportSession) -> MoveOperation | None:
        """Return the file operation selected for this import."""
        if session.config["move"].get(bool):
            return MoveOperation.MOVE
        if session.config["copy"].get(bool):
            return MoveOperation.COPY
        if session.config["link"].get(bool):
            return MoveOperation.LINK
        if session.config["hardlink"].get(bool):
            return MoveOperation.HARDLINK

        reflink = session.config["reflink"].get()
        if reflink == "auto":
            return MoveOperation.REFLINK_AUTO
        if reflink:
            return MoveOperation.REFLINK

        return None

    def _is_reimport(self, session: ImportSession) -> bool:
        """Whether this import is operating on files already in the library."""
        library_path = _to_path(session.lib.directory)
        return any(
            _to_path(import_path).is_relative_to(library_path)
            for import_path in session.paths
        )

    def _on_item_moved(self, item: Item, source: Any, destination: Any) -> None:
        self._record_item_move(item, source, destination, MoveOperation.MOVE)

    def _on_item_copied(self, item: Item, source: Any, destination: Any) -> None:
        self._record_item_move(item, source, destination, MoveOperation.COPY)

    def _on_item_linked(self, item: Item, source: Any, destination: Any) -> None:
        self._record_item_move(item, source, destination, MoveOperation.LINK)

    def _on_item_hardlinked(self, item: Item, source: Any, destination: Any) -> None:
        self._record_item_move(item, source, destination, MoveOperation.HARDLINK)

    def _on_item_reflinked(self, item: Item, source: Any, destination: Any) -> None:
        self._record_item_move(item, source, destination, MoveOperation.REFLINK_AUTO)

    def _record_item_move(
        self,
        item: Item,
        source: Any,
        destination: Any,
        operation: MoveOperation,
    ) -> None:
        """Remember a move performed outside an import, such as by ``beet mv``."""
        if self._import_active:
            return

        with self._lock:
            self._item_moves.append(
                ItemMove(
                    album_id=getattr(item, "album_id", None),
                    source=_to_path(source),
                    destination=_to_path(destination),
                    operation=operation,
                )
            )

    def _on_cli_exit(self, lib: Library) -> None:
        """Process queued imports and file moves once the command has finished."""
        with self._lock:
            jobs = list(self._jobs)
            item_moves = list(self._item_moves)
            imported_paths = set(self._imported_paths)
            toppath_roots = {
                toppath: set(roots) for toppath, roots in self._toppath_roots.items()
            }
            self._import_active = False
            self._jobs.clear()
            self._item_moves.clear()
            self._imported_paths.clear()
            self._task_sources.clear()
            self._toppath_roots.clear()

        if not jobs and not item_moves:
            return

        library_root = _to_path(lib.directory)
        duplicate_action: DuplicateAction = self.config["duplicate_action"].as_choice(
            ["merge", "skip", "keep", "remove"]
        )

        processed_roots: list[Path] = []

        for job in jobs:
            source_root = self._source_root(job, toppath_roots)
            destination_root = _common_parent(job.destination_items)

            if source_root is None:
                self._log.warning(
                    "Could not determine release root for {}.",
                    job.destination_items[0],
                )
                continue
            if destination_root is None:
                self._log.warning(
                    "Could not determine destination directory for {}.",
                    source_root,
                )
                continue
            if destination_root == library_root:
                destination_root = job.destination_items[0].parent
            if not source_root.exists():
                self._log.debug(
                    "Release root no longer exists: {}",
                    source_root,
                )
                continue
            if source_root != destination_root and destination_root.is_relative_to(
                source_root
            ):
                self._log.warning(
                    "Destination {} is inside release root {}; skipping.",
                    destination_root,
                    source_root,
                )
                continue

            conflicting_root = next(
                (
                    root
                    for root in processed_roots
                    if root == source_root
                    or root.is_relative_to(source_root)
                    or source_root.is_relative_to(root)
                ),
                None,
            )
            if conflicting_root is not None:
                self._log.warning(
                    "Skipping release root {}: it overlaps already processed root {}.",
                    source_root,
                    conflicting_root,
                )
                continue

            processed_roots.append(source_root)
            self._process_release(
                source_root=source_root,
                destination_root=destination_root,
                imported_paths=imported_paths,
                operation=job.operation,
                delete_source=job.delete_source,
                is_reimport=job.is_reimport,
                duplicate_action=duplicate_action,
            )

        self._process_item_moves(
            lib=lib,
            moves=item_moves,
            library_root=library_root,
            duplicate_action=duplicate_action,
            processed_roots=processed_roots,
        )

    def _process_item_moves(
        self,
        lib: Library,
        moves: list[ItemMove],
        library_root: Path,
        duplicate_action: DuplicateAction,
        processed_roots: list[Path],
    ) -> None:
        """Move the remaining album contents after a move outside an import.

        This covers workflows such as ``beet import .`` followed by ``beet mv``,
        where the import leaves files in place and the actual move happens in a
        separate command.
        """
        if not moves:
            return

        groups: dict[tuple[str, object], list[ItemMove]] = {}
        for move in moves:
            key: tuple[str, object]
            if move.album_id is not None:
                key = ("album", move.album_id)
            else:
                key = ("item", move.source.parent)
            groups.setdefault(key, []).append(move)

        library_paths = tuple(_to_path(item.path) for item in lib.items())

        for group in groups.values():
            sources = tuple(move.source for move in group)
            destinations = tuple(move.destination for move in group)
            source_root = _common_parent(sources)
            destination_root = _common_parent(destinations)
            operation = group[0].operation

            if source_root is None or destination_root is None:
                continue
            if source_root == destination_root:
                continue
            if source_root == library_root:
                self._log.debug("Not scanning the library root for release files.")
                continue
            if not source_root.exists():
                continue
            if destination_root == library_root:
                destination_root = destinations[0].parent
            if destination_root.is_relative_to(source_root):
                self._log.warning(
                    "Destination {} is inside release root {}; skipping.",
                    destination_root,
                    source_root,
                )
                continue

            # Only act when the album moved as a unit. If a library item still
            # points into the source directory, the move was partial and the
            # remaining audio must stay where it is.
            if any(path.is_relative_to(source_root) for path in library_paths):
                self._log.debug(
                    "Not moving extras for partial move of {}.",
                    source_root,
                )
                continue

            conflicting_root = next(
                (
                    root
                    for root in processed_roots
                    if root == source_root
                    or root.is_relative_to(source_root)
                    or source_root.is_relative_to(root)
                ),
                None,
            )
            if conflicting_root is not None:
                self._log.warning(
                    "Skipping release root {}: it overlaps already processed root {}.",
                    source_root,
                    conflicting_root,
                )
                continue

            processed_roots.append(source_root)
            self._process_release(
                source_root=source_root,
                destination_root=destination_root,
                imported_paths=set(sources),
                operation=operation,
                delete_source=False,
                is_reimport=False,
                duplicate_action=duplicate_action,
            )

    def _source_root(
        self, job: MoveJob, toppath_roots: dict[Path, set[Path]]
    ) -> Path | None:
        """Determine which directory represents the imported release."""
        base_root = _common_parent(job.source_items)

        if job.toppath is not None and job.toppath.is_dir():
            roots = toppath_roots.get(job.toppath, set())
            if len(roots) <= 1:
                return job.toppath

        return base_root or job.toppath

    def _process_release(
        self,
        source_root: Path,
        destination_root: Path,
        imported_paths: set[Path],
        operation: MoveOperation,
        delete_source: bool,
        is_reimport: bool,
        duplicate_action: DuplicateAction,
    ) -> None:
        """Move every non-imported file from ``source_root`` to the library."""
        label = "Moving" if is_reimport else OPERATION_LABELS[operation]
        ignore = [util.bytestring_path(path) for path in config["ignore"].as_str_seq()]
        ignore_hidden = config["ignore_hidden"].get(bool)

        for root, _dirs, files in util.sorted_walk(
            util.bytestring_path(source_root),
            ignore=ignore,
            ignore_hidden=ignore_hidden,
            logger=self._log,
        ):
            for filename in files:
                source = Path(os.fsdecode(os.path.join(root, filename)))

                if source in imported_paths:
                    self._log.debug("Skipping imported audio: {}", source)
                    continue

                destination = destination_root / source.relative_to(source_root)

                self._process_file(
                    source=source,
                    destination=destination,
                    source_root=source_root,
                    operation=operation,
                    delete_source=delete_source,
                    is_reimport=is_reimport,
                    duplicate_action=duplicate_action,
                    label=label,
                )

    def _process_file(
        self,
        source: Path,
        destination: Path,
        source_root: Path,
        operation: MoveOperation,
        delete_source: bool,
        is_reimport: bool,
        duplicate_action: DuplicateAction,
        label: str,
    ) -> None:
        """Move, copy, link, or skip one release file."""
        if source == destination:
            return

        replace = False

        if destination.exists():
            try:
                identical = destination.is_file() and filecmp.cmp(
                    source, destination, shallow=False
                )
            except (OSError, util.FilesystemError) as exc:
                self._log.error(
                    "Could not compare {} and {}: {}", source, destination, exc
                )
                return

            if identical:
                if operation is MoveOperation.MOVE or is_reimport or delete_source:
                    self._remove_source(source, source_root)
                else:
                    self._log.debug(
                        "Skipping identical file already in destination: {}",
                        destination,
                    )
                return

            if duplicate_action == "skip":
                self._log.debug(
                    "Skipping {}: destination already exists ({}).",
                    source,
                    destination,
                )
                return
            if duplicate_action == "remove":
                replace = True
            else:
                destination = Path(util.unique_path(str(destination)))

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._log.info(
                "{}: {} -> {}",
                label,
                source,
                destination,
            )
            self._transfer(
                source,
                destination,
                operation=operation,
                is_reimport=is_reimport,
                replace=replace,
            )
        except (OSError, util.FilesystemError) as exc:
            self._log.error("Could not process {}: {}", source, exc)
            return

        if operation is MoveOperation.MOVE or is_reimport:
            self._prune(source, source_root)
        elif delete_source:
            self._remove_source(source, source_root)

    def _transfer(
        self,
        source: Path,
        destination: Path,
        operation: MoveOperation,
        is_reimport: bool,
        replace: bool,
    ) -> None:
        """Apply the selected beets file operation."""
        source_bytes = util.bytestring_path(source)
        destination_bytes = util.bytestring_path(destination)

        if operation is MoveOperation.MOVE or is_reimport:
            util.move(source_bytes, destination_bytes, replace=replace)
        elif operation is MoveOperation.COPY:
            util.copy(source_bytes, destination_bytes, replace=replace)
        elif operation is MoveOperation.LINK:
            util.link(source_bytes, destination_bytes, replace=replace)
        elif operation is MoveOperation.HARDLINK:
            util.hardlink(source_bytes, destination_bytes, replace=replace)
        elif operation is MoveOperation.REFLINK:
            util.reflink(
                source_bytes,
                destination_bytes,
                replace=replace,
                fallback=False,
            )
        elif operation is MoveOperation.REFLINK_AUTO:
            util.reflink(
                source_bytes,
                destination_bytes,
                replace=replace,
                fallback=True,
            )
        else:
            raise AssertionError(f"Unknown operation: {operation}")

    def _remove_source(self, source: Path, source_root: Path) -> None:
        """Remove a source file after it has been copied or already existed."""
        try:
            util.remove(util.bytestring_path(source), False)
        except (OSError, util.FilesystemError) as exc:
            self._log.error("Could not remove {}: {}", source, exc)
            return

        self._prune(source, source_root)

    def _prune(self, source: Path, source_root: Path) -> None:
        """Remove empty directories left behind by a move."""
        util.prune_dirs(
            util.bytestring_path(source.parent),
            root=util.bytestring_path(source_root.parent),
            clutter=config["clutter"].as_str_seq(),
        )
