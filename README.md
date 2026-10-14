# beets-plugins

A collection of plugins for [beets](https://beets.io/).

## movextra

Moves the remaining contents of an imported release into the imported music's
destination directory. Beets still handles the audio; `movextra` handles everything
else, including files that beets otherwise ignores.

- Follows the active import operation: `move`, `copy`, `link`, `hardlink`, or `reflink`.
- Never touches audio files that beets imported.
- Preserves subdirectories, so `Scans/front.jpg` stays under `Scans/`.
- Handles album and single-track imports.
- Prunes empty source directories after a move.
- Honors beets' global `ignore`, `ignore_hidden`, and `clutter` settings.

### Configuration

```yaml
plugins: movextra

movextra:
  duplicate_action: merge
```

`duplicate_action` controls what happens when the destination already contains a file
with the same name:

- `merge` (default): skip identical files; keep differing files with a unique name.
- `skip`: keep the existing destination file and leave the source file alone.
- `keep`: always keep both files by giving the new one a unique name.
- `remove`: overwrite the existing destination file.

### Behavior notes

- With `import.copy` plus `import.delete`, source extras are removed after copying.
- Reimports behave like beets reimports: copy/link operations are treated as moves for
  files already inside the library.
- Query-based imports (`beet import -L ...`) are not handled because they have no
  release directory to scan.
- When multiple imported albums share one source directory, only the first album
  processes that directory to avoid moving files into the wrong album.
