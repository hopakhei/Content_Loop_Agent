# Slide background photos

Drop a real image here and point a slide (or a whole carousel) at it:

```json
{ "image": "backgrounds/experience-curve-cover.jpg",
  "image_dim": 0.55, "image_blur": 3 }
```

- `image_dim` — how hard the dark scrim covers the photo. `0.80` (default) is
  the safe setting for a content slide; `0.5–0.6` suits a cover, which carries
  far less text. `0` shows the raw photo and will usually break legibility.
- `image_blur` — Gaussian radius. Blur is what stops photo detail from fighting
  the characters; drop it only on covers.
- A slide with both `image` and `motif` uses the photo; a missing file falls
  back to the motif, so a half-finished set still renders.

Images are committed and composited at render time — carousel-drip never
fetches anything at run time. Keep them ≥1080×1350 (4:5) so the cover-fit
crop has pixels to work with.
