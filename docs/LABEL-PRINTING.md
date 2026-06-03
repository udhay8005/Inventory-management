# Label Printing — Thermal 4×2 inch

All WMS labels print on the **thermal printer** as **4 × 2 inch (101.6 × 50.8 mm) die-cut stickers**. A4 sheet labels have been removed — there is one label format for everything.

## Hardware
- **Printer:** TSC TE244, 203 DPI, USB
- **Label stock:** 4 × 2 inch die-cut labels with a **gap** between each sticker
- **Scanner:** Helett HT20pro (reads 1D + 2D)

## Print a label
1. Open a list — **Products**, or **WMS → Operations → Compartments / Slots / Racks**.
2. Tick the records you want.
3. **Print** menu → **WMS Product Label (4×2 in)** or **WMS Location Label (4×2 in)**.
4. Send the PDF to the TE244.

*(Onboarding a new product offers its label automatically at the end.)*

## What's on the label
- **Title** (product / location name) across the top
- **SKU / full path** on the second line
- A large **Code128 barcode** filling the lower half, with the number under the bars
- Optional **logo** in the top-right corner (upload it in Label Settings)

## Make it "follow the gap" — one-time printer setup
The labels are die-cut with a gap; the printer must **detect that gap** so every print lands squarely on a sticker. The PDF page is exactly one label — the printer's gap sensor advances across the gap to the next.

**A. TE244 driver (Windows → Devices and Printers → right-click TE244 → Printing preferences):**
1. **Stock / Page size:** 101.6 × 50.8 mm (≈ 100 × 50). Save as a "USER" stock if prompted.
2. **Media Type:** **Gap / Labels with gaps** — *not* Continuous, *not* Black-mark.
3. **Gap height:** your label's gap (default **3 mm**; see Label Settings → "Gap between labels").
4. Apply.

**B. Calibrate the gap sensor (teach the printer the gap):**
- **Button method:** printer on + labels loaded → press and hold **FEED** until it feeds 1–2 labels and stops. It has measured the gap.
- **Or** TSC *Diagnostic Tool / Printer Utility* → **Calibrate Sensor → Gap**.
- After calibration, one **FEED** press should advance **exactly one label** and stop at the gap.

**C. Test ONE label first** (print a single record). It should sit centered with the gap above/below. If it drifts down each print or spits blanks, re-run **B** and confirm Media Type = **Gap** (A.2).

## Re-style the sticker
**WMS → Configuration → Label Settings** lets you (no code):
- set the **label size** + **gap between labels**,
- move the **logo / title / SKU / barcode** (in millimetres) and set font sizes,
- **show/hide** any element (set a width or height to **0** to hide it),
- upload your trust's **logo**.

Change a value, reprint, watch it move.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Prints across two labels / drifts down each print | Media Type must be **Gap**; re-calibrate (B) |
| Feeds a blank label between prints | Stock height too tall — set 50.8 mm; re-calibrate |
| Right edge clipped | Stock width must be ≤ 101.6 mm in the driver |
| Barcode won't scan | Increase barcode height in Label Settings; clean the print head |
