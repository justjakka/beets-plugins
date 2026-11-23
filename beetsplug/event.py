import mediafile
import mutagen
from beets import util
from beets.plugins import BeetsPlugin


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
        except Exception:
            return

        item["genres"] = current_genres
        item.store()
