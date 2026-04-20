"""
LLM-powered auto-tagging for photos.

Sends the small image variant to a vision-capable LLM and parses the returned
tags. Designed to run inside a Celery task after photo processing completes.
"""
import base64
import json
import logging

from django.conf import settings
from django.utils.text import slugify

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a photo tagging assistant. Given a photograph, return a JSON array of 3-8 descriptive tags.

Rules:
- Tags should be lowercase, 1-3 words each
- Include tags for: subject matter, setting/environment, mood/style, colors, and photographic style
- Be specific but not overly niche (e.g. "golden hour" not "photo taken at 6:47pm")
- Do not include tags about image quality or resolution
- Return ONLY a JSON array of strings, no other text

Example output: ["mountain landscape", "sunset", "golden hour", "snow peaks", "warm tones", "wide angle"]"""


def generate_tags_for_image(image_bytes: bytes, content_type: str = "image/jpeg") -> list[str]:
    """
    Send image bytes to an LLM vision model and return a list of tag strings.
    Returns an empty list if tagging is disabled or fails.
    """
    if not settings.AUTO_TAG_ENABLED or not settings.AUTO_TAG_API_KEY:
        return []

    try:
        import openai
    except ImportError:
        logger.warning("openai package not installed, skipping auto-tagging")
        return []

    client_kwargs = {"api_key": settings.AUTO_TAG_API_KEY}
    if settings.AUTO_TAG_BASE_URL:
        client_kwargs["base_url"] = settings.AUTO_TAG_BASE_URL

    client = openai.OpenAI(**client_kwargs)

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64_image}"

    try:
        response = client.chat.completions.create(
            model=settings.AUTO_TAG_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Tag this photo:"},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                    ],
                },
            ],
            max_tokens=200,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        tags = json.loads(raw)
        if isinstance(tags, list):
            return [str(t).strip().lower()[:100] for t in tags if t and str(t).strip()]
        return []
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("Failed to parse LLM tag response: %s", exc)
        return []
    except Exception as exc:
        logger.exception("Auto-tagging LLM call failed: %s", exc)
        return []


def apply_tags_to_photo(photo, tag_names: list[str]):
    """
    Given a Photo instance and a list of tag name strings, get-or-create Tag
    objects and associate them with the photo.
    """
    from .models import Tag

    if not tag_names:
        return

    tags = []
    for name in tag_names:
        slug = slugify(name)
        if not slug:
            continue
        tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": name})
        tags.append(tag)

    if tags:
        photo.tags.set(tags)
