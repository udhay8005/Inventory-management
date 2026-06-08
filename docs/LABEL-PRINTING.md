# Label Printing — Thermal 4×1 inch (100×25 mm)

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
4. Send the PDF to the TE244.

*(Onboarding a new product offers its label automatically at the end.)*

## What's on the label
A ~1 inch **logo zone** on the left and a ~3 inch **content zone** on the right:
- **Logo** (optional) — left
- **Title** (product / location name) — top of the right zone
- **SKU / full path** — second line
- **Code128 barcode** + the number under the bars — bottom of the right zone

## Make it "follow the gap" — one-time printer setup
The labels are die-cut with a gap; the printer must **detect that gap** so every print lands squarely on a sticker. The PDF page is exactly one 100×25 mm label — the printer's gap sensor advances across the gap to the next.

**A. TE244 driver (Windows → Devices and Printers → right-click TE244 → Printing preferences):**
1. **Stock / Page size:** 100 × 25 mm. Save as a "USER" stock if prompted.
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
- set the **label size** (defaults 100×25 mm) + **gap between labels**,
- move the **logo / title / SKU / barcode** (in millimetres) and set font sizes,
- **show/hide** any element (set a width or height to **0** to hide it),
- upload your trust's **logo**.

Change a value, reprint, watch it move.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Prints across two labels / drifts down each print | Media Type must be **Gap**; re-calibrate (B) |
| Feeds a blank label between prints | Stock height too tall — set 25 mm; re-calibrate |
| Right edge clipped | Stock width must be ≤ 100 mm in the driver |
| Barcode won't scan | Increase barcode height in Label Settings; clean the print head |
