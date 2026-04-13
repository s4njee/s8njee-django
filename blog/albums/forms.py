from django import forms
from django.core.exceptions import ValidationError
from .models import Album, Photo


ACCEPTED_EXTENSIONS = {
    # Standard image formats
    'jpg', 'jpeg', 'png', 'webp', 'gif', 'avif', 'heic', 'heif',
    # RAW camera formats
    'nef', 'cr2', 'cr3', 'dng', 'arw', 'orf', 'raf', 'rw2',
}


def validate_photo_extension(value):
    ext = value.name.rsplit('.', 1)[-1].lower()
    if ext not in ACCEPTED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file type '.{ext}'. Accepted: {', '.join(sorted(ACCEPTED_EXTENSIONS))}"
        )


class AlbumForm(forms.ModelForm):
    class Meta:
        model = Album
        fields = ["title", "description"]


class PhotoForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ["image", "caption"]


class MultiPhotoForm(forms.Form):
    """Form for uploading multiple photos at once, including RAW camera files."""
    images = forms.FileField(
        validators=[validate_photo_extension],
        widget=forms.ClearableFileInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["images"].widget.attrs["multiple"] = True
        self.fields["images"].widget.attrs["accept"] = (
            "image/*,.nef,.cr2,.cr3,.dng,.arw,.orf,.raf,.rw2"
        )
