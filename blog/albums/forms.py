from PIL import Image, UnidentifiedImageError

from django import forms
from django.core.exceptions import ValidationError

from .image_processing import RAW_EXTENSIONS
from .models import Album, Photo, PhotoStatus


ACCEPTED_EXTENSIONS = {
    # Standard image formats
    'jpg', 'jpeg', 'png', 'webp', 'gif', 'avif', 'heic', 'heif',
    # RAW camera formats
    'nef', 'cr2', 'cr3', 'dng', 'arw', 'orf', 'raf', 'rw2',
}


def validate_photo_upload(value):
    ext = value.name.rsplit('.', 1)[-1].lower()
    if ext not in ACCEPTED_EXTENSIONS:
        raise ValidationError("The uploaded file is not a supported image.")
    if ext not in RAW_EXTENSIONS:
        try:
            image = Image.open(value)
            image.verify()
            value.seek(0)
        except (UnidentifiedImageError, OSError) as exc:
            raise ValidationError("The uploaded file is not a supported image.") from exc


class AlbumForm(forms.ModelForm):
    cover_photo = forms.ModelChoiceField(
        queryset=Photo.objects.none(),
        required=False,
        label="Cover photo",
        help_text="Select the photo to use as the album cover.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if getattr(self.instance, "pk", None):
            self.fields["cover_photo"].queryset = (
                Photo.objects.filter(album=self.instance, status=PhotoStatus.READY)
                .exclude(image="")
                .order_by("sort_order", "-uploaded_at")
            )
        else:
            self.fields["cover_photo"].widget = forms.HiddenInput()

    class Meta:
        model = Album
        fields = ["title", "slug", "description", "cover_photo"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Album title"}),
            "slug": forms.TextInput(attrs={"placeholder": "album-slug"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Add a short description for this album.",
                }
            ),
        }

    def clean_cover_photo(self):
        cover_photo = self.cleaned_data.get("cover_photo")
        if cover_photo and cover_photo.album_id != self.instance.pk:
            raise ValidationError("Choose a cover photo from this album.")
        return cover_photo


class AlbumDeleteForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="I understand this will delete the album and all of its photos.",
    )


class PhotoUploadForm(forms.Form):
    image = forms.FileField(
        validators=[validate_photo_upload],
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/*,.nef,.cr2,.cr3,.dng,.arw,.orf,.raf,.rw2"}
        ),
    )


class PhotoEditForm(forms.ModelForm):
    replace_image = forms.FileField(
        required=False,
        validators=[validate_photo_upload],
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/*,.nef,.cr2,.cr3,.dng,.arw,.orf,.raf,.rw2"}
        ),
        label="Replace image",
    )

    class Meta:
        model = Photo
        fields = ["caption", "alt_text"]
        widgets = {
            "caption": forms.TextInput(attrs={"placeholder": "Add a caption"}),
            "alt_text": forms.TextInput(attrs={"placeholder": "Describe image for SEO/accessibility"}),
        }


class PhotoDeleteForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="I understand this will delete the photo and its files.",
    )


class MultiPhotoForm(forms.Form):
    """Form for uploading multiple photos at once, including RAW camera files."""
    images = forms.FileField(
        validators=[validate_photo_upload],
        widget=forms.ClearableFileInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["images"].widget.attrs["multiple"] = True
        self.fields["images"].widget.attrs["accept"] = (
            "image/*,.nef,.cr2,.cr3,.dng,.arw,.orf,.raf,.rw2"
        )
