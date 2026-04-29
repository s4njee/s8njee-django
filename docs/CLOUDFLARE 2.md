# Cloudflare Products for This Project

Suggestions for paid Cloudflare products that are hobbyist-priced and would
genuinely pay off for this Django photoblog. Prices are "indicative, 2026" —
re-check before committing.

The current stack: Django on netcup K8s, Postgres, Celery/Valkey, optional
`django-storages` S3 backend for media, Whitenoise for static files. That shapes
what's actually useful below.

---

## Tier 1 — Strong Fit, Clear Win

### R2 (Object Storage) — replace S3 for photo media

The big one. R2 is S3-API compatible, so it drops into the existing
`django-storages` wiring with only endpoint/credential changes.

*   **Why it's a win:**
    *   **No egress fees.** S3 charges ~$0.09/GB out; R2 charges $0. For a
        photoblog where every page view streams images, this is the single
        biggest long-term saving.
    *   **Free tier is meaningful:** 10 GB storage, 1M Class A ops/month,
        10M Class B ops/month. Most hobbyist photoblogs fit under the free tier
        entirely.
    *   **Paid tier past free:** $0.015/GB-month storage, $4.50/M Class A,
        $0.36/M Class B. 100 GB of photos ≈ **$1.35/month**.
*   **Where it plugs in:** [blog/blog/settings/base.py:113](blog/blog/settings/base.py#L113)
    already branches on `AWS_STORAGE_BUCKET_NAME`. Point `AWS_S3_ENDPOINT_URL`
    at `https://<account-id>.r2.cloudflarestorage.com` and replace the custom
    domain with a public R2 bucket URL (or a Worker in front — see below).
*   **Gotcha:** R2's public bucket URLs don't support per-object cache-control
    headers as flexibly as CloudFront. If that matters, front R2 with a Worker
    or Cloudflare CDN via a custom domain.

#### R2 photo migration runbook

Cloudflare calls this product **R2**, not R1. The safe migration path for this
project is to copy the existing S3 object keys into R2 unchanged, then flip the
Django media storage settings. The database should not need a data migration as
long as keys such as `photos/...` and `blog-images/...` stay identical.

**Before changing production**

*   **Add R2 settings support first.** The current settings file defines
    `AWS_S3_CUSTOM_DOMAIN` as `<bucket>.s3.amazonaws.com` and does not currently
    read `AWS_S3_ENDPOINT_URL`. Before cutover, update the app to read:
    *   `AWS_S3_ENDPOINT_URL=https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com`
    *   `AWS_S3_REGION_NAME=auto`
    *   `AWS_S3_CUSTOM_DOMAIN=<media-domain>`
    *   existing `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and
        `AWS_STORAGE_BUCKET_NAME`
    The settings shape should be roughly:

    ```python
    AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL')
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_S3_CUSTOM_DOMAIN = env('AWS_S3_CUSTOM_DOMAIN')

    if AWS_STORAGE_BUCKET_NAME:
        STORAGES['default'] = {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        }
        if AWS_S3_CUSTOM_DOMAIN:
            MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    ```

    `django-storages` reads the module-level `AWS_S3_ENDPOINT_URL`; the missing
    piece is defining it from the environment before the storage backend starts.
*   **Use a custom domain for production media.** Prefer something like
    `media.s8njee.com` connected directly to the R2 bucket. Use the generated
    `r2.dev` URL only for smoke tests; Cloudflare treats it as a development URL.
*   **Keep the old S3 bucket.** Do not delete `s8njee-photoblog` until the site
    has served from R2 for at least a few days and uploads have been verified.
*   **Decide whether DB backups move too.** `DB_BACKUP_BUCKET` currently points
    at S3-style storage. Migrate photo media first. Move database backups later
    only after the backup command also supports the R2 endpoint.

**1. Inventory the current S3 bucket**

Use the current AWS credentials/profile for the existing bucket.

```sh
aws s3 ls s3://s8njee-photoblog/ --recursive --summarize
aws s3 ls s3://s8njee-photoblog/photos/ --recursive --summarize
aws s3 ls s3://s8njee-photoblog/blog-images/ --recursive --summarize
```

Save a few known-good object keys for later smoke tests:

```sh
aws s3 ls s3://s8njee-photoblog/photos/ --recursive | head
```

**2. Create the R2 bucket**

In Cloudflare Dashboard:

1.  Go to **Storage & databases > R2 > Overview**.
2.  Create a bucket. Use `s8njee-photoblog` if available, otherwise choose a
    new name such as `s8njee-photoblog-media`.
3.  Copy the Cloudflare account ID.
4.  Create an R2 API token with **Object Read & Write** access scoped to this
    bucket.
5.  Copy the Access Key ID and Secret Access Key immediately; the secret is only
    shown once.

**3. Configure a local R2 AWS CLI profile**

R2 uses the S3 API, but every AWS CLI command must include the R2 endpoint.

```sh
export CLOUDFLARE_ACCOUNT_ID="<account-id>"
export R2_ENDPOINT_URL="https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
export R2_BUCKET="s8njee-photoblog-media"

aws configure --profile cloudflare-r2
aws --profile cloudflare-r2 --endpoint-url "$R2_ENDPOINT_URL" s3 ls
```

For the profile prompts:

```text
AWS Access Key ID: <R2 access key id>
AWS Secret Access Key: <R2 secret access key>
Default region name: auto
Default output format: json
```

**4. Make a local mirror of the existing S3 media**

Use a local mirror instead of trying to copy S3 to R2 directly with one AWS CLI
command. Direct bucket-to-bucket copy is awkward because the source S3 bucket
and destination R2 bucket use different credentials and endpoints.

```sh
mkdir -p /tmp/s8njee-photoblog-media
aws s3 sync s3://s8njee-photoblog/ /tmp/s8njee-photoblog-media/ --dryrun
aws s3 sync s3://s8njee-photoblog/ /tmp/s8njee-photoblog-media/
```

If the bucket is large, run this from a machine with enough disk space and a
stable network connection.

**5. Upload the mirror to R2**

Dry-run first, then run the real upload.

```sh
aws --profile cloudflare-r2 --endpoint-url "$R2_ENDPOINT_URL" \
  s3 sync /tmp/s8njee-photoblog-media/ "s3://${R2_BUCKET}/" --dryrun

aws --profile cloudflare-r2 --endpoint-url "$R2_ENDPOINT_URL" \
  s3 sync /tmp/s8njee-photoblog-media/ "s3://${R2_BUCKET}/"
```

Verify object counts and sample keys:

```sh
aws s3 ls s3://s8njee-photoblog/ --recursive | wc -l
aws --profile cloudflare-r2 --endpoint-url "$R2_ENDPOINT_URL" \
  s3 ls "s3://${R2_BUCKET}/" --recursive | wc -l

aws --profile cloudflare-r2 --endpoint-url "$R2_ENDPOINT_URL" \
  s3 ls "s3://${R2_BUCKET}/photos/" --recursive | head
```

**6. Attach a public media domain**

In the R2 bucket settings:

1.  Add a custom domain such as `media.s8njee.com`.
2.  Wait until the domain status is active.
3.  Test a known object from step 1:

```sh
curl -I "https://media.s8njee.com/photos/<known-object-key>"
```

Expected result: `200` for an existing object, with image content type headers.

**7. Update Freya configuration first**

After the app supports R2 endpoint/custom-domain settings, update the Freya
configuration and secret material:

```text
AWS_STORAGE_BUCKET_NAME=<R2 bucket name>
AWS_S3_REGION_NAME=auto
AWS_S3_ENDPOINT_URL=https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com
AWS_S3_CUSTOM_DOMAIN=media.s8njee.com
AWS_ACCESS_KEY_ID=<R2 access key id>
AWS_SECRET_ACCESS_KEY=<R2 secret access key>
```

Then deploy through the existing script-based Freya flow:

```sh
scripts/freya-sync.sh --rollout
kubectl --context=freya rollout status deploy/s8njee-web -n s8njee-web
```

Smoke test:

*   Open a public album page and verify existing photos load from the R2 media
    domain.
*   Open the admin upload flow and upload one new test photo.
*   Confirm the new object appears in R2:

```sh
aws --profile cloudflare-r2 --endpoint-url "$R2_ENDPOINT_URL" \
  s3 ls "s3://${R2_BUCKET}/photos/" --recursive | tail
```

**8. Run a final delta sync before netcup cutover**

If the site accepted uploads while the first copy was running, run one final
sync before switching netcup/production traffic. Ideally pause uploads for a
short maintenance window.

```sh
aws s3 sync s3://s8njee-photoblog/ /tmp/s8njee-photoblog-media/
aws --profile cloudflare-r2 --endpoint-url "$R2_ENDPOINT_URL" \
  s3 sync /tmp/s8njee-photoblog-media/ "s3://${R2_BUCKET}/"
```

Then apply the same environment changes to the netcup deployment or Argo-managed
production manifests.

**9. Rollback plan**

Rollback is configuration-only if object keys are unchanged:

1.  Restore the old S3 values for `AWS_STORAGE_BUCKET_NAME`,
    `AWS_S3_REGION_NAME`, credentials, and custom domain behavior.
2.  Roll the deployment.
3.  If users uploaded new photos while R2 was active, copy those new R2 objects
    back to S3 before or immediately after rollback.

Do not delete or lifecycle-expire the old S3 objects until rollback is no longer
needed.

**10. Cleanup after the migration is stable**

After several days of successful page views and uploads:

*   Remove stale AWS S3 credentials from Kubernetes secrets.
*   Decide whether to migrate `DB_BACKUP_BUCKET` separately.
*   Disable any temporary `r2.dev` public access if a custom domain is active.
*   Add a lifecycle or archival policy to the old S3 bucket instead of deleting
    it immediately.

**Cloudflare-native alternative:** Cloudflare also has R2 data migration tools
called Super Slurper and Sippy. Those are useful for larger buckets or low
downtime migrations. For this project, the local mirror approach is easier to
audit, produces a reusable backup, and avoids changing the live app until after
the objects are already present in R2.

Useful Cloudflare references:

*   [R2 S3-compatible API](https://developers.cloudflare.com/r2/api/s3/api/)
*   [Use R2 with S3 tools and SDKs](https://developers.cloudflare.com/r2/get-started/s3/)
*   [R2 public buckets and custom domains](https://developers.cloudflare.com/r2/data-access/public-buckets/)
*   [R2 migration strategies](https://developers.cloudflare.com/r2/data-migration/migration-strategies/)

### Cloudflare CDN (free) + Cache Rules (Pro, $25/month — skip unless needed)

Zero-plan Cloudflare is free and probably already enough. Mention it here only
to flag the upgrade path.

*   **What's free:** Global CDN, automatic TLS, basic DDoS, 3 Page Rules, brotli.
    For a static-ish photoblog this is often all you need.
*   **Pro ($25/mo) only if:** you want Image Resizing via URL, WebP/AVIF auto
    conversion from CDN (Polish), or advanced cache rules. At hobby scale the
    existing `srcset`/variants pipeline already handles format conversion, so
    Pro is usually **not worth it**.

### Images ($5/month base) — only if you kill the variant pipeline

Cloudflare Images stores originals and serves arbitrary resize/format variants
on demand from a URL. You currently build variants yourself in Celery
([blog/albums/image_processing.py](blog/albums/image_processing.py)).

*   **Pricing:** $5/month for 100k stored images + 500k delivered, then
    $1/100k stored, $1/100k delivered.
*   **Why you might want it:** replaces the srcset generation task, the
    regenerate-variants command, and all the variant storage. One URL per
    size/format, no pre-computation.
*   **Why you might not:** you've already built the variant pipeline, and
    eliminating it means giving up local control over compression/quality.
    Only worth it if you're tired of maintaining the task queue for image work.

---

## Tier 2 — Useful if You Grow Into Them

### Workers (free tier → $5/month Paid)

Small JS/Python runtime at Cloudflare's edge. Free tier: 100k requests/day.
Paid: $5/month for 10M requests, sub-ms cold start.

*   **Concrete uses for this site:**
    *   **Signed-URL issuer** for the "share a draft" idea in `IDEAS.md`
        (§ Signed Preview Links). Worker validates the signature at the edge
        before the request reaches Django — cheaper and faster than a Django
        round-trip.
    *   **Dynamic OG cards** (§ 8 in the new IDEAS). Generate social-share
        images at the edge and cache on Cloudflare. Avoids running Pillow in
        the request path.
    *   **Image resize proxy in front of R2** if you skip Cloudflare Images:
        a Worker with `@cf-wasm/photon` or Cloudflare's `cf.image` binding
        resizes on demand.
*   **Verdict:** Worth $5/month once you have one concrete use. Skip until
    then.

### KV or D1 (both have free tiers)

Edge key-value / SQLite-at-edge. Free for hobby use.

*   **Concrete uses:**
    *   **KV:** cache rendered post HTML at the edge for logged-out users.
        Trivial speed-up with a Worker in front.
    *   **D1:** probably not useful — you have Postgres already, and a split
        data store adds complexity without a payoff at this scale.
*   **Verdict:** KV only if you put a Worker in front. D1 is over-engineered
    for this site.

### Turnstile (free)

CAPTCHA replacement. Free. If you ever add a contact form or the "share a
draft" preview endpoint needs light bot protection, this is the drop-in.

*   **Verdict:** Free and one-line Django form integration. No reason not to
    use when a form appears.

### Tunnel / Zero Trust (free for up to 50 users)

`cloudflared` tunnel exposes your Django admin without opening an ingress on
netcup.

*   **Concrete use:** lock `/admin/` behind Cloudflare Access (Google/GitHub
    SSO, IP allow-list, device posture) without changing Django auth. A
    single-user hobby site fits trivially in the free tier.
*   **Verdict:** Genuinely useful — reduces admin surface area to zero public
    ingress. Worth setting up.

---

## Tier 3 — Probably Skip

### Argo Smart Routing ($5/month + $0.10/GB)

Routes traffic over Cloudflare's backbone. Real but marginal latency
improvement. Not worth it for a hobby photoblog where user latency is
dominated by image byte-sizes, not TCP round trips.

### Load Balancing ($5/month + $0.50/origin)

Multi-origin failover. You have one netcup pod. No value.

### Stream ($5/month per 1k minutes stored)

Video hosting/transcoding. No video on the site. Skip unless that changes.

### Pages / Workers Sites

Static hosting. Conceptually interesting *if* you implement the
`django-distill` static-export idea in `IDEAS.md` (§ 12). At that point Pages
becomes the free host for the exported site. Until then, no.

### Email Routing (free)

Free catchall for the domain if you want `hello@s8njee.com`. Useful, trivial,
not really a "product" decision.

---

## Suggested Adoption Order

1.  **R2 for photos** — highest ROI, drop-in. Move media off S3 this weekend.
2.  **Cloudflare Tunnel + Access in front of `/admin/`** — free, removes
    public admin ingress.
3.  **Email Routing** — free, ten-minute setup.
4.  **Workers ($5/mo)** — only when the first concrete use case lands
    (signed drafts, OG cards, or image resize proxy).
5.  **Cloudflare Images** — only if you decide to retire the self-built
    variant pipeline. Not a recommended swap yet; the current pipeline works.

---

## Rough Monthly Cost

| Setup                                      | Expected cost     |
| ------------------------------------------ | ----------------- |
| Free tier only (CDN, Tunnel, Email, DNS)   | $0                |
| + R2 for ~50 GB of photos                  | ~$0.75            |
| + Workers Paid (when a use case appears)   | +$5               |
| + Cloudflare Images (if variant swap)      | +$5 base          |
| **Realistic steady-state**                 | **~$0.75–$11/mo** |

Compare to the current S3 cost on typical traffic: egress alone usually
exceeds all of the above combined.
