from django import forms
from django.utils.text import slugify

from .models import Post


class PostEditorForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    class Meta:
        model = Post
        fields = ["title", "slug", "content", "published"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Post title"}),
            "slug": forms.TextInput(attrs={"placeholder": "post-slug"}),
            "content": forms.Textarea(
                attrs={
                    "rows": 24,
                    "placeholder": "# Start writing in Markdown\n\nUse headings, lists, code fences, links, and images.",
                    "spellcheck": "true",
                }
            ),
        }

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        title = self.cleaned_data.get("title", "").strip()
        return slug or slugify(title)
