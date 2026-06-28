import mediafile
from beets.plugins import BeetsPlugin


class Event(BeetsPlugin):
    def __init__(self):
        field = mediafile.MediaField(
            mediafile.MP3DescStorageStyle("event"), mediafile.StorageStyle("event")
        )
        self.add_media_field("event", field)
