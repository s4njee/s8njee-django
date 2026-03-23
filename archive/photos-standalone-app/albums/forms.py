from django import forms
from .models import Album, Photo


class AlbumForm(forms.ModelForm):
    class Meta:
        model = Album
        fields = ["title", "description"]


class PhotoForm(forms.ModelForm):
    class Meta:
        model = Photo
        fields = ["image", "caption"]


class MultiPhotoForm(forms.Form):
    """Form for uploading multiple photos at once."""
    images = forms.ImageField(widget=forms.ClearableFileInput())

    class Media:
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Force multiple attribute at render time
        self.fields["images"].widget.attrs["multiple"] = True
        self.fields["images"].widget.attrs["accept"] = "image/*"
