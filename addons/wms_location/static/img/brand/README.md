# Dakshin Vrindavan — brand assets

Logos for the Dakshin Vrindavan Gaushala WMS.

| File | Use | Format | Notes |
|------|-----|--------|-------|
| `app-logo.jpg` | **App logo** | JPEG, horizontal | Full "dakshin vrindavan — Care for cows" lockup. For app branding / headers / login / docs. |
| `label-logo.png` | **Label logo** | PNG, square (transparent) | Stacked logo with flute + peacock feather. Used on printed labels. |

Stored here (the core `wms_location` module's `static/`) so the assets are
version-controlled and web-served at:

- `/wms_location/static/img/brand/app-logo.jpg`
- `/wms_location/static/img/brand/label-logo.png`

**Printed thermal labels** use the square colour logo (`label-logo.png`), copied
into the label engine at `wms_barcode/static/img/label_logo.png`, where it is
dithered to 1-bit for the TE244. Note: on a ~176-dot logo zone the colour
detail (flute + peacock feathers) dithers to a halftone; the wordmark stays
readable. The black wordmark (`app-logo.jpg`) is the crisper alternative if a
cleaner 1-bit logo is wanted later. The app icon
(`static/description/icon.png`) is not wired up yet — ask when needed.
