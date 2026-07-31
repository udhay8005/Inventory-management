# Dakshin Vrindavan — brand assets

Logos for the Dakshin Vrindavan Gaushala WMS.

| File | Use | Format | Notes |
|------|-----|--------|-------|
| `app-logo.jpg` | **App logo** | JPEG, horizontal | Full "dakshin vrindavan — Care for cows" lockup. For app branding / headers / login / docs. |
| `label-logo.png` | **Label logo** | PNG, square | Black "dakshin vrindavan / Care for cows" wordmark. Used on printed thermal labels. |

Stored here (the core `wms_location` module's `static/`) so the assets are
version-controlled and web-served at:

- `/wms_location/static/img/brand/app-logo.jpg`
- `/wms_location/static/img/brand/label-logo.png`

**Printed thermal labels** use `label-logo.png`, copied into the label engine at
`wms_barcode/static/img/label_logo.png`, where it is dithered to 1-bit for the
TE244. It is a black wordmark on white, so it dithers crisply (no halftone) in
the label's bordered ~1-inch logo zone. The label engine renders that logo big
on the LEFT (full label height, framed) with the brand line / product name /
sub-line / barcode stacked to its right. Because a long structured SKU barcode
at a scannable module width nearly spans the whole label, it cannot also be wide
*and* sit beside a logo this big — the owner chose the big logo, so the barcode
uses the narrower 1-dot module (it still scans; it just doesn't fill its zone).
The app icon (`static/description/icon.png`) is not wired up yet — ask when
needed.
