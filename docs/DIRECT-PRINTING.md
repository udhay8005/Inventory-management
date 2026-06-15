# Direct Label Printing (TSC TE244)

Print barcode labels **straight to the thermal printer with one click** — no
Chrome print box, no PDF download, no scaling or alignment fiddling. Select the
products or locations, choose the printer and how many copies, press **Print**,
and the labels come out.

This replaces the old "download a PDF and fight the browser print dialog" flow as
the **primary** way to print. (The PDF labels still exist as a fallback.)

---

## How it works (in one line)

The WMS server runs on the **same Windows PC** as the printer, so it sends the
printer's own language (**TSPL**) straight to the Windows print spooler. Because
TSPL carries the label size itself, the output is always exact-size and upright —
the browser can never shrink or rotate it again.

No QZ Tray, no Java, no browser extension, no extra program to keep running.

---

## One-time setup (Admin)

**WMS → Configuration → Label Printers**

A printer called **"Thermal label printer"** (the TSC TE244) is already set up.
To check or change it, open it and:

1. Click **Detect printers** — shows the exact Windows printer names this PC can
   see. The **Windows printer name** must match one of them (e.g. `TSC TE244`).
2. Check the **Label media**: Width `100 mm`, Height `25 mm`, Gap `3 mm`,
   `203` dpi (the True-Ally stock).
3. Click **Test print** — a sample label should come out, upright and full-size.
4. If it sits slightly off the sticker, nudge **Shift right (mm)** /
   **Shift down (mm)** and test again. If it's too light, raise **Density**.

To add another printer (e.g. a network one), click **New**, choose
**Network (IP)**, and enter its IP address (raw port 9100).

Only **Managers** can add or edit printers.

---

## Printing labels (everyone)

You can print from any of these lists (or a single record's form):

| To print… | Go to | 
|---|---|
| **Product** labels | the Products list |
| **Rack** labels | WMS → Configuration → Racks |
| **Slot** labels | WMS → Operations → Slots |
| **Compartment** labels | WMS → Configuration → Compartments |

Then:

1. **Tick** one or many rows (or open a single record).
2. Open the **Action** menu (the ⚙ gear at the top) → **Print labels (direct)**.
3. Choose the **Printer** and **Copies** (copies = how many of *each* label).
4. Click **Print**.

The labels print immediately and a green "Labels sent to printer" message appears.
**Reprint** = just do it again. Records without a barcode are skipped (with a note).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Printer '…' was not found on the server" | Open **Configuration → Label Printers → Detect printers**, then set the **Windows printer name** to the exact match. Check the printer is on. |
| Nothing prints, no error | Confirm the printer is online in Windows (Printers & scanners) and not paused. |
| Print is too light / too dark | Raise / lower **Density** on the printer profile. |
| Sits slightly off the sticker | Adjust **Shift right / Shift down (mm)** and **Test print**. |
| Drifts down each label / blanks between | Calibrate the printer's gap sensor once: hold the printer **FEED** button until it feeds 1–2 labels and stops. |
| Barcode won't scan | Make sure the record has a real barcode; raise **Density**; clean the print head. |
| Server isn't on Windows / printer on another PC | Use a **Network (IP)** printer profile, or fall back to the PDF label (Print menu) at **Actual size / 100%** — see [LABEL-PRINTING.md](LABEL-PRINTING.md). |

---

## Security

- Only **Managers** can add, edit, or delete printer profiles, or run a Test
  print (Configuration is manager-only).
- **Store Keepers** can print labels but cannot change printer settings.
- The server only ever sends a label job to a **pre-configured** printer profile;
  there is no arbitrary command execution and no secret is logged.

---

## What was deliberately *not* built (and why)

Following the project's "simplest reliable thing" rule, these were skipped because
a single USB printer on the server PC doesn't need them — each is easy to add
later if the setup grows:

- **Offline print queue + retry daemon** — the printer is local and either on or
  off; a clear error + reprint is simpler and loses nothing.
- **Multi-PC / remote printing** — if storekeepers later print from other PCs,
  share the printer from this PC or add a Network (IP) printer profile.
- **QZ Tray / WebUSB bridges** — unnecessary because the server is the print host.
