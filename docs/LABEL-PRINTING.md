# Label Printing — Thermal 4×1 inch (100×25 mm)

> **Print with one click — use Direct Printing.**
> The recommended way to print is now **direct to the printer** (no browser print
> box, no PDF, no scaling): select records → **Action → Print labels (direct)**.
> See **[DIRECT-PRINTING.md](DIRECT-PRINTING.md)**. The PDF method below is kept as
> a **fallback** (e.g. if the server ever runs on a non-Windows host).

All WMS labels print on the **thermal printer** as **4×1 inch (100×25 mm) die-cut stickers** — the **True-Ally** direct-thermal roll the trust uses. A4 sheet labels have been removed: there is one label format for everything.

## Hardware
- **Printer:** TSC TE244, 203 DPI, USB
- **Label stock:** **True-Ally 100×25 mm (4×1 inch)** die-cut direct-thermal, ~1000/roll, with a **gap** between each sticker
- **Scanner:** Helett HT20pro (reads 1D + 2D)

## Who sees which source list
Labels can be printed from several places, but **what you see in the menu depends on your role**:

| Role | Can reach | Cannot reach |
|---|---|---|
| **Store Keeper** (`group_wms_user`) | Products list; **Operations → Slots** (and the **Print Label** button on the slot form) | Racks, Compartments, Label Settings (entire **Configuration** submenu is manager-only) |
| **Manager** (`group_wms_manager`) | Products list; Operations → Slots; **Configuration → Racks**, **Compartments**, **Label Settings** | — |

If you're a Store Keeper and can't find Racks or Compartments in the menu, that's expected — ask a manager to print rack/compartment labels for you.

## Print a label
1. Open a list — **Products**, **WMS → Operations → Slots**, or **WMS → Configuration → Racks / Compartments** (manager-only).
2. Tick the records you want.
3. **Print** menu → **WMS Product Label (100×25mm)** or **WMS Location Label (100×25mm)**.
4. Send the PDF to the TE244 **at Actual size / 100% scaling** — see the print-dialog note below.

*(Onboarding a new product offers its label automatically at the end.)*

## Print at Actual size / 100% — NOT "Fit to page"
The PDF page is already exactly one 100×25 mm label. When you send it to the TE244, the print dialog (browser, Adobe Reader, or the Windows print pane) **must keep the scaling at "Actual size" / "100%"**.

If you leave it on **"Fit to page" / "Shrink to fit"** (the usual default), the viewer rescales the 100×25 mm page to fit the driver's paper, which **shrinks the whole label into one corner** and **narrows the Code128 bars below what the scanner can read**. The placement (logo left, barcode right) and the bar widths only come out correctly at 100%.

- Adobe Reader: Print → **Page Sizing & Handling** → **Actual size**.
- Browser print: **More settings → Scale → 100%** (Default usually means Fit; set it explicitly).
- Confirm the preview shows one full label edge-to-edge, not a small label with white margins.

## What's on the label
A ~1 inch **logo zone** on the left and a ~3 inch **content zone** on the right:
- **Logo** (optional) — left
- **Title** (product / location name) — top of the right zone
- **SKU / full path** — second line
- **Code128 barcode** + the number under the bars — bottom of the right zone

## Make it "follow the gap" — one-time printer setup
The labels are die-cut with a gap; the printer must **detect that gap** so every print lands squarely on a sticker. The PDF page is exactly one 100×25 mm label — the printer's gap sensor advances across the gap to the next.

**A. TE244 driver (Windows → Devices and Printers → right-click TE244 → Printing preferences):**
1. **Stock / Page size:** 100 × 25 mm (4 × 1 inch). Save as a "USER" stock if prompted.
2. **Media Type:** **Gap / Labels with gaps** (die-cut) — *not* Continuous, *not* Black-mark.
3. **Gap height:** your label's gap (default **3 mm**; see Label Settings → "Gap between labels").
4. **Print quality / resolution:** **203 DPI** — this matches the report's paper format, so the bars raster 1:1 onto the sticker.
5. Apply.

**B. Calibrate the gap sensor (teach the printer the gap):**
- **Button method:** printer on + labels loaded → press and hold **FEED** until it feeds 1–2 labels and stops. It has measured the gap.
- **Or** TSC *Diagnostic Tool / Printer Utility* → **Calibrate Sensor → Gap**.
- After calibration, one **FEED** press should advance **exactly one label** and stop at the gap.

**C. Test ONE label first** (print a single record). It should sit centered with the gap above/below. If it drifts down each print or spits blanks, re-run **B** and confirm Media Type = **Gap** (A.2).

## Re-style the sticker
**WMS → Configuration → Label Settings** lets you (no code):
- set the **label size** (defaults 100×25 mm) + **gap between labels**,
- move the **logo / title / SKU / barcode** (in millimetres) and set font sizes,
- **show/hide** any element (set a width or height to **0** to hide it),
- upload your trust's **logo**.

The label **content layout** (logo in the left 1 inch, barcode + text in the right 3 inch) is set in **WMS → Configuration → Label Settings** — not in the printer driver. The shipped defaults already give logo-LEFT / barcode-RIGHT; the printer setup above only governs the stock size, the gap, and the scaling.

Change a value, reprint, watch it move.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Label prints tiny in a corner with white margins / barcode won't scan after a viewer change | Scaling is on "Fit to page" — set the print dialog to **Actual size / 100%** |
| Prints across two labels / drifts down each print | Media Type must be **Gap**; re-calibrate (B) |
| Feeds a blank label between prints | Stock height too tall — set 25 mm; re-calibrate |
| Right edge clipped | Stock width must be ≤ 100 mm in the driver |
| Barcode won't scan | Increase barcode height in Label Settings; clean the print head |
