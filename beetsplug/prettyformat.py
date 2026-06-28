from beets.library import Album
from beets.plugins import BeetsPlugin


class PrettyFormat(BeetsPlugin):
    def __init__(self) -> None:
        super().__init__()
        self.album_template_fields["label_or_aa"] = _tmpl_label_or_aa
        self.album_template_fields["aa_after_label"] = _tmpl_aa_after_label


def _tmpl_label_or_aa(item: Album) -> str:
    if item.label:
        return item.label
    else:
        if item.albumartist_credit:
            return item.albumartist_credit
        elif item.albumartists_credit:
            return item.albumartists_credit
        elif item.albumartist:
            return item.albumartist
        elif item.albumartists:
            return item.albumartists
        else:
            return ""


def _tmpl_aa_after_label(item: Album) -> str:
    if item.label:
        if item.albumartist_credit:
            return item.albumartist_credit + " — "
        elif item.albumartists_credit:
            return item.albumartists_credit + " — "
        elif item.albumartist:
            return item.albumartist + " — "
        elif item.albumartists:
            return item.albumartists + " — "
        else:
            return ""
    else:
        return ""
