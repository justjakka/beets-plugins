import logging

import mediafile
import mutagen
from beets import util
from beets.plugins import BeetsPlugin

log = logging.getLogger("beets.genrefix")


class Event(BeetsPlugin):
    def __init__(self):
        super().__init__()
        field = mediafile.MediaField(
            mediafile.MP3DescStorageStyle("EVENT"),
            mediafile.StorageStyle("EVENT"),
        )
        self.add_media_field("event", field)
        self.register_listener("write", self.on_write)

    def _read_genres(self, item):
        real_path = util.syspath(item.path)
        try:
            audio = mutagen.File(real_path, easy=True)
            if "genre" in audio:
                genres = audio["genre"]

                if isinstance(genres, str):
                    genres = [genres]

                return genres

        except Exception:
            return []

        return []

    def on_write(self, item, path, tags):
        try:
            current_genres = self._read_genres(item)
        except Exception as exc:
            log.debug(f"Could not read tags from {path}: {exc}")
            return

        old_genres = item.get("genres", [])
        item["genres"] = current_genres
        log.info(
            f"Updated genres for '{item.title}' from {old_genres} to {current_genres}"
        )
        item.store()
