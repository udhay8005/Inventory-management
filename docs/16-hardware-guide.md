# 16 — Hardware Buying Guide

Cheat sheet for picking scanners, printers, and supporting hardware. None
of this is mandatory — the system works with whatever you already have —
but these are the patterns that fit best.

## Will *any* USB / wireless barcode scanner work?

**Almost certainly yes.** Pick any scanner that:

| Must have | Why |
|---|---|
| **HID Keyboard** mode (default on 99% of scanners) | The scanner types into the focused field, no driver needed |
| **CR/LF (Enter) suffix** | So scans auto-submit instead of just sitting in the field |
| **Code 128** support | That's the symbology we print |
| **EAN-13 / UPC-A** support | For factory product barcodes |
| **USB or 2.4 GHz dongle or Bluetooth HID** | Any of these is fine |

The two Amazon products you linked are **typical 2.4 GHz wireless scanners**.
Both fit the "must have" list. If you bought either today and plugged in
the dongle, you'd open *WMS → Operations → Scan Receipt*, the cursor
would already be in the scan field, you'd scan a barcode, and a line
would appear. No code change needed on our side.

### Things to verify in the seller listing

- "Works as USB keyboard / HID" or "no driver required"
- "Enter / CR / LF after scan" or "configurable suffix" (almost always
  default-on; if not, scan a setup barcode from the manual once)
- Wireless range you actually need — 10 m is plenty inside a small warehouse
- Battery life (rechargeable Li-ion = no AAA-battery hunt)

### Things you can ignore

- "Wedge mode" vs "POS mode" — wedge mode IS HID-keyboard mode, that's fine
- "Compatible with Windows / Mac / Linux" — it'll work; HID is OS-agnostic
- "Built-in memory / batch mode" — we don't need it (every scan goes
  straight into Odoo)
- "Programmable" — useful but not required

## Recommended budget tiers

| Tier | What you get | When |
|---|---|---|
| **Cheap & cheerful (₹800 – ₹1,500)** | Wired USB scanner, 1D only, no battery | Single fixed scan station |
| **Wireless basic (₹1,500 – ₹3,000)** | 2.4 GHz dongle, rechargeable, 1D | Walk-the-floor receiving / issue |
| **Bluetooth + 2D (₹3,000 – ₹6,000)** | BT-HID, scans QR codes too, longer range | Multi-station / tablet workflow |
| **Industrial (₹8,000+)** | IP54 rated, drop-tested, longer battery | Outdoor / rough handling |

For your "32 racks + open floor + 2nd-floor" setup, the **₹1,500 – ₹3,000 wireless** tier is the sweet spot. Buy 2 — one fixed at receiving, one for floor walking.

## Label printer choices

| Option | Cost | What it does | Recommendation |
|---|---|---|---|
| **Your existing A4 inkjet/laser + sticker sheets** | ₹0 (you have one) | Prints 24-up sticker sheets via the WMS Location Label report | **Start here.** Buy Avery L7159 or generic 24-up A4 stickers (~₹200/100 sheets). |
| **Thermal label printer (Zebra GK420t, TSC TE244)** | ₹15,000 – ₹25,000 | Direct-print individual stickers, faster, no waste | Only worth it after 1-2 months of A4 sticker usage when you've grown tired of it |

Stay on A4 stickers for at least the first month. The thermal printer is a productivity upgrade, not a requirement.

## Where each hardware piece goes in your layout

```
Receiving dock
  ├─ Wireless scanner #1  (always paired with the laptop here)
  ├─ A4 printer + stickers (label new products on the spot)
  └─ Laptop on UPS (so power blink doesn't lose mid-scan picking)

Storage area (32 racks + floor zones)
  ├─ Wireless scanner #2 (taken on the rounds)
  └─ Optional phone-as-scanner over WiFi for spot checks

Issue / despatch
  └─ Wireless scanner #1 or #2 (whichever is free)
```

## Compatibility test before you commit to a model

Five minutes once the scanner arrives:

1. Plug in the USB dongle (or pair via Bluetooth).
2. Open Notepad. Scan any barcode (e.g. from a snack packet).
3. You should see the digits + the cursor jump to a new line.
   - **Digits only, no newline** → scanner is missing the Enter suffix. Look in the manual for "Set Enter Suffix" or "CR/LF" — there's a config barcode to enable it.
   - **Nothing appears** → driver or pairing issue. Check Windows Device Manager.
   - **Both work** → ready for production.
4. Open `http://localhost:8069` → WMS → Scan Receipt → tap the scan field → scan a product. Line should appear with no clicks needed.

If those four steps pass, the scanner is fully compatible.

## Power & network

| Item | Need | Notes |
|---|---|---|
| UPS for the host PC | 600 VA minimum | 10-min runtime is enough — Postgres survives power-cut anyway, but in-flight scans are saved |
| WiFi router / AP | Decent dual-band | If using phones / tablets, place an AP close to receiving |
| Network cable to host PC | Cat6 if possible | Reliable beats fast for warehouse use |

## When to upgrade

| Symptom | Upgrade |
|---|---|
| Operators waste >2 min/day waiting for the A4 printer | Buy a thermal label printer (Zebra GK420t) |
| Wireless scanner range fails between racks | Add a second 2.4 GHz dongle or upgrade to BT |
| Phone scanning over WiFi is slow or drops | Add a cheap AP near receiving |
| Multiple operators stepping on each other in Scan Receipt | Train them — the wizard is per-session, conflicts are rare. But if real, dedicate one scanner per operator instead of sharing |

## Floor / non-rack storage hardware

Same scanners work. For floor zone labels, an A4 sticker sheet is still fine — print 24-up labels and stick them on the floor, on pallet uprights, or on a placard next to the area.

Plastic sleeves or laminating the floor labels is worth the ₹5/sheet so they survive forklift dust.

## Summary

For the immediate setup you proposed, this is enough:

- Any 2.4 GHz wireless USB scanner (₹1,500-₹3,000 range)
- Your existing A4 printer
- A pack of 24-up A4 sticker sheets (~₹200)
- The 600 VA UPS already in your starter list
- Existing WiFi router

Total spend: **under ₹4,000 for everything not already on hand.** Add a thermal label printer only after you've actually deployed and felt the friction.
