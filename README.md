# Render QA

Check how faithfully an AI render keeps the geometry of your SketchUp or Vectorworks view.

Drop in the model view and the AI render (from Leonardo, Gendo, Veras, Vectorworks AI Visualizer or anything else) and Render QA gives you:

- a score out of 100;
- a traffic light;
- a picture showing exactly what the AI moved, removed or invented.

**Your images never leave the office.** Everything runs on your own computer. Nothing is uploaded to the internet.

---

## For designers

### Opening it

Double-click **Render QA** in the Render QA folder. It opens in your web browser after a few seconds.

- On a Mac the file is called `Render QA.command`. On Windows it's `Render QA.bat`.
- If your office shares Render QA from one computer, just open the link you were sent instead.

It keeps running in the background, so double-clicking again simply reopens it.

### Check a render

1. Drag your **original model view** (a screenshot or export from SketchUp or Vectorworks) into the left box.
2. Drag the **AI render** into the right box.
3. Pick which AI tool made it. Render QA guesses from the file name if it can.
4. *Optional:* switch on **Skip some areas** and paint over anything you don't care about, such as floors, walls, sky or people. Painted areas aren't scored.
5. Press **Check render**.

You'll get:

| Score | Light | Meaning |
|---|---|---|
| 85 and up | 🟢 **Accurate** | The render kept your geometry. |
| 65–84 | 🟠 **Check closely** | Mostly faithful, but some things changed. |
| Under 65 | 🔴 **Geometry changed a lot** | Check before using this render. |

The **What changed** picture marks the differences:

- **Red:** missing or moved from your model.
- **Blue:** added by the AI.
- **Grey:** areas you asked to skip.

Use the **fade slider** to flick between your model and the render. **Download report** gives you a one-page PDF (or PNG) with both images, the markup, the score and the tool name. It's ready to attach to an email or a project folder.

> A high score can still hide one important change, such as a missing light fitting. When that happens, Render QA says "Mostly accurate, but 2 areas look different", so glance at the highlighted spots.

### Compare AI tools

Use this to find out which AI tool suits your projects best.

1. Each **job** is one model view plus the renders different tools made from it. Add the model view, then drop in all the renders. Set the AI tool for each render.
2. Press **Add another job** for more views. Three to five jobs give a fair comparison.
3. Press **Run all checks**.

The leaderboard ranks the tools by average score, as a chart and as a table. Open any job to see what each tool changed. You can download a **summary image** for sharing and a **CSV** for Excel.

### Tips for fair results

- Export the render at the **same camera view** as the model screenshot. Render QA lines up small shifts and zooms automatically, but it can't compare different camera angles and will warn you.
- Hide UI clutter (axes, section planes, selection highlights) before taking the model screenshot.
- PNG, JPG and WEBP all work. Very large images are scaled down automatically.

---

## For the office admin

### One-time setup

You need Python 3.11 or newer. The setup script checks, and opens the download page if it's missing.

**Mac**

1. Put the Render QA folder somewhere permanent, for example Applications or a shared drive.
2. Open the **Admin** folder and double-click **Set up (Mac)**.
   - macOS may say it "can't be opened because it is from an unidentified developer". If so, right-click it, choose **Open**, then **Open** again. This is only needed for this one file. Setup unblocks the others.
3. Wait for "All done" (a few minutes, needs internet this one time).

**Windows**

1. Put the Render QA folder somewhere permanent.
2. Open the **Admin** folder and double-click **Set up (Windows)**.
   - If Windows SmartScreen appears, click **More info → Run anyway**.
   - If you need to install Python, tick **Add python.exe to PATH** in the installer.
3. Wait for "All done".

Setup installs everything into a private `.venv` folder inside Render QA. Nothing else on the computer changes. To uninstall, delete the folder.

Designers can then double-click **Render QA**. Consider putting a shortcut or alias on their desktops or in the Dock.

### Sharing it on the office network

Run Render QA on one computer, and everyone else opens it in their browser with a link. Nobody else needs to install anything.

1. On the computer that will host it, run setup as above.
2. In the **Admin** folder, double-click **Share on office network**.
3. It shows a link like `http://192.168.1.20:8520`. Send that link to the team. It's also shown at the bottom of every Render QA page on that computer.
4. The first time, allow the firewall prompt. On a Mac, "Allow Python to accept incoming connections". On Windows, allow on **private** networks.

Keep the host computer switched on and awake. If it restarts, double-click **Share on office network** again, since sharing mode doesn't come back on its own after a restart.

Images are processed on the host computer. They travel only across your office network and are never stored on disk. Only share on a trusted office network, never on public Wi-Fi.

To give the host a link that doesn't change, ask your IT provider to reserve its IP address on the router.

### Stopping it

Render QA uses very little while idle, so there's usually no need to stop it. It stops when the computer restarts. To stop it now, double-click **Stop Render QA** in the Admin folder.

### Updating

Replace the files with the new version, keeping `settings.json` if you've saved custom settings. Then run **Set up** again.

### If something goes wrong

- **"Render QA isn't set up yet":** run Set up (see above).
- **It won't start:** the details are in `logs/render-qa.log`. Running **Set up** again fixes most problems.

---

## Privacy

- All image processing happens locally with OpenCV. No AI models, no cloud services, no accounts.
- Uploaded images live only in memory while the app is open. They are never written to disk.
- Streamlit's usage statistics are switched off (`.streamlit/config.toml`).
- Streamlit's one built-in internet lookup is also switched off. In sharing mode it would normally look up the computer's public IP address; `serve.py` disables that.
- The only time Render QA uses the internet is during setup, to download its components.

---

## Fine-tuning (Advanced settings)

At the bottom of each screen, **Advanced settings** holds these controls. Most offices never need them.

- **Line detail in the model view / in the render.** This controls how faint a line must be before it counts.
  - Keep the render's detail lower: wood grain, tiles, shadows and reflections aren't geometry.
  - Press **Preview detection** to see the lines found in each image side by side, and adjust until the render's lines show walls, joinery and fixtures but not textures.
- **How far a line can move and still match.** The default is 4 pixels, measured on the image scaled to 1600 pixels wide. Raise it if tiny wobbles are being flagged.
- **Score thresholds** for Accurate and Check closely.
- **If the render is a different shape** (for example the AI made it wider):
  - trim the edges (the default);
  - add borders;
  - stretch it.
- **Line the images up automatically.** On by default.

**Save as default for everyone** stores the settings in `settings.json` in the Render QA folder. They then apply every time it starts, for everyone using that computer or its shared link. **Reset to defaults** undoes changes.

### How the score works

1. The render is resized, trimmed or padded to match the model view, then lined up automatically.
   - Two alignment methods are tried: matching distinctive points, and lining up the drawn lines directly.
   - An alignment is only kept if it improves the match.
2. Lines are picked out of both images with Canny edge detection.
   - The render gets extra smoothing and stricter thresholds to ignore texture.
   - Specks are discarded.
3. The two sets of lines are compared, allowing a small tolerance (distance transform).
   - Model lines with no render line nearby are **missing** (red).
   - Render lines with nothing in the model nearby are **added** (blue).
4. The score is the F1 of the two:
   - **recall** is the share of model lines kept;
   - **precision** is the share of render lines that belong to the model.

   Ignored areas are excluded before scoring.

---

## For developers

```
app.py              Streamlit entry point (navigation between the two screens)
serve.py            Starts Streamlit with its external-IP lookup disabled
launcher.py         Start/stop in the background; used by the double-click files
core/               Image logic: no Streamlit imports
  imageio.py          loading, format checks, downscaling
  align.py            fit to shape, feature-based and line-based alignment
  edges.py            line detection and sensitivity mapping
  compare.py          tolerant comparison, recall/precision/F1, Chamfer distance
  overlay.py          red/blue markup and problem-area counting
  pipeline.py         check_render(): the whole check in one call
  report.py           PNG/PDF report and comparison summary
  settings.py         defaults, thresholds, settings.json
ui/                 Streamlit screens, theme and custom components
  components/         brush mask painter and fade slider (plain HTML/JS)
tests/              Synthetic-image tests
samples/            Example model view and renders to try
Admin/              Setup, sharing and stop scripts
```

Run the tests:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
```

```bash
.venv/bin/python -m pytest -q
```

Run the app in the foreground while developing:

```bash
.venv/bin/python serve.py run app.py
```
