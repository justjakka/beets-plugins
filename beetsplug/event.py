import mediafile
from beets.plugins import BeetsPlugin


class Event(BeetsPlugin):
    def __init__(self):
        super().__init__()
        field = mediafile.MediaField(
            mediafile.MP3DescStorageStyle("EVENT"), mediafile.StorageStyle("EVENT")
        )
        self.add_media_field("event", field)
