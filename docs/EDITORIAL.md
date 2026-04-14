# Editorial Workflow

How to create, preview, publish, and correct content on s8njee.com.
Requires staff login. All URLs are relative to the site root.

---

## Blog Posts

### Create a draft

1. Go to `/editor/posts/new/`
2. Fill in **Title** — the slug auto-generates from it; leave the Slug field blank unless you want a custom one.
3. Write in the **Markdown editor** (Toast UI, markdown-only mode). The right panel renders a live preview using the same sanitizer the public site uses — what you see there is exactly what readers see.
4. Leave **Publish this post to the public site** unchecked.
5. Click **Save Post**. The post is saved as a draft and the editor reloads with a "Successfully Saved" confirmation.

Drafts are completely invisible to the public. The public URL (`/<slug>/`) returns a 404 until published. There is no shareable preview URL.

### Embed images

In the editor toolbar, click the image icon (or drag a file directly into the editor). The image uploads to the `blog-images/` path in the storage backend and the Markdown reference is inserted automatically. Accepted formats: AVIF, JPEG, PNG, GIF, WebP. Limit: 10 MB per image.

To reference a photo from the gallery instead, copy its URL from the album and insert it manually as a Markdown image: `![alt text](https://…)`.

### Publish

Open the post in the editor (`/editor/posts/<slug>/`), check **Publish this post to the public site**, and save. The post immediately appears on the public list at `/` and is accessible at `/<slug>/`.

### Correct a published post

Go to `/editor/posts/<slug>/` — there is a **View Live Post** link at the top-right of the editor for convenience. Edit the content, save. The public page updates immediately. `updated_at` is stamped automatically; `created_at` (used for archive routing and ordering) does not change.

There is no version history. If you need to preserve the old text, copy it before saving.

### Unpublish

Open the post in the editor, uncheck **Publish this post to the public site**, save. The public URL returns a 404 again immediately.

### Change a slug

Edit the Slug field in the editor and save. **Warning:** this breaks any existing inbound links and bookmarks — there is no automatic redirect. Only change a slug before publishing, or treat it as a deliberate redirect-breaking rename.

### Admin access

`/admin/posts/post/` gives a filterable list with bulk publish/unpublish actions and is useful for managing many posts at once. The admin does not have the live preview panel; use the editor for drafting.

---

## Photo Albums

### Create an album

1. Click **+ New Album** in the nav (staff only), or go to `/photos/create/`.
2. Fill in **Title** and optionally **Description**.
3. Optionally set a **Slug** for a readable URL (`/photos/s/<slug>/`). If left blank the album is only accessible via UUID URL (`/photos/<uuid>/`). The slug can be set later via Edit Album.
4. Save. The album is created and immediately publicly visible — there is no draft state for albums.

### Upload photos

From the album detail page, click **+ Upload Photos**. Drop files or click to select. Accepted formats: JPEG, PNG, AVIF, WebP, HEIC, and RAW (NEF, CR2, CR3, DNG, ARW, ORF, RAF, RW2).

Up to 3 photos upload concurrently. Each file shows its own progress bar and status:

| Status | Meaning |
|--------|---------|
| Uploading… | File is transferring to the server |
| Processing… | Server is converting to AVIF, extracting EXIF, generating variants |
| ✓ | Ready — visible in the album |
| Failed | Processing error — error text shown; Retry button appears |

RAW files are converted to AVIF. All photos are downscaled to 1920px on the longest edge. Three size variants are generated: full (1920px), medium (1200px), small (800px). A 400px thumbnail is also generated for the grid view.

After upload, click **View Album** to return to the album.

### Add captions and alt text

From the album detail page, click **Edit** on any photo. Two fields:

- **Caption** — displayed below the photo in the lightbox. Also used as the `alt` attribute fallback if Alt Text is not set.
- **Alt Text** — the meaningful description for screen readers and search engines. Set this for every photo. It is shown to users who cannot see the image and is indexed by search engines.

Save returns to the album.

### Reorder photos

Drag photo cards into the desired order on the album detail page. Order saves automatically after you drop a card (a brief "Order saved" confirmation appears). Reordering does not affect existing permalink hashes — those are UUID-based.

### Set the album cover

Click **Set as Album Cover** on any ready photo. The chosen photo appears as the cover thumbnail on the album list page. If no cover is set, the first ready photo is used automatically.

### Replace a photo

Click **Edit** on the photo, use the **Replace image** field to upload a new file, and save. The old image, thumbnail, and variants are deleted from storage and the new file is queued for processing. The photo keeps its existing caption, alt text, sort order, and permalink.

### Delete a photo

Click **Delete** on the photo card (requires confirmation). The photo record and all associated files (image, variants, thumbnail) are removed from storage.

### Delete an album

Click **Delete Album** on the album detail page (requires confirmation). All photos and their files are deleted before the album record is removed.

### Share a photo permalink

In the lightbox, click **Copy link** in the sidebar to copy the stable photo URL to your clipboard. The URL format is `/<album-path>/#photo-<uuid>` and is stable across reordering.

A server-side redirect also exists at `/photos/<album_pk>/photos/<photo_pk>/` — useful for linking from other systems where a hash URL is awkward. It 302-redirects to the album page with the lightbox hash appended.

---

## What Is Not Supported Yet

- **Drafts for albums** — albums are public the moment they are created.
- **Scheduled publishing** — there is no "publish at" date/time; toggling the published flag is manual.
- **Unpublished post preview URL** — unpublished posts return a 404 at their public URL; preview is only available inside the editor.
- **Post version history** — saves overwrite; copy text before making major changes if you need a backup.
- **Captions at upload time** — captions and alt text are set after upload via the Edit screen.
