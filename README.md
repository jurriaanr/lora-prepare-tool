# Lora Prepare Tool — A Lora Dataset Preparation Tool

A cross-platform GUI tool for cropping images into a **square frame** with pixel-perfect control, designed for preparing datasets (e.g., for training LoRA models).

## ✨ Features

- **Interactive cropping**:
  - Click and drag the image to position it within a square frame.
  - Mouse-wheel zoom (supports fine zoom with `Ctrl`/`⌘` held).
  - **Snapping**: when dragging, edges within 10px of the frame snap perfectly.
  - **Arrow key nudging** (1px steps) — only active when the image area is focused.

- **Frame options**:
  - Frame sizes: `512`, `768`, or `1024` pixels.
  - Fit image fully inside frame or cover frame completely (cropping as needed).
  - Dimmed (50% opacity) background outside the frame for clear visual boundaries.
  - Frame and window layout **persist across sessions**.

- **Image queue management**:
  - Select multiple images; process sequentially.
  - **Save & Next**: crops the image to the frame, saves as JPEG, writes `.txt` tags file.
  - **Skip**: moves to the next image without cropping.
  - Processed originals are moved to a `processed/` folder automatically.
  - Cropped images + `.txt` metadata are saved in an `output/` folder.

- **Metadata tagging**:
  - **Global words**: Always added to `.txt` files first. Saved in `global_words.txt` and loaded at startup.
  - **Per-image notes**: Specific tags for the current image.
  - Tag suggestions based on history (words used in ≥2 images).
  - Suggestions are **alphabetically sorted** for predictability.
  - Tag history saved in `suggest_history.txt` (semicolon-separated) and persisted.

- **Smart text handling**:
  - Tags are deduplicated **per image**.
  - Tags are combined from global + per-image notes in order, separated by `, `.
  - Both `,` and newlines are accepted as separators when entering tags.

- **Quality-of-life**:
  - Clicking the image area with no image loaded opens the file chooser.
  - Works on Windows, macOS, and Linux (cross-platform Tkinter + Pillow).
  - Selection in text areas does not get lost when dragging outside the widget.
  - After last image is saved or skipped, the viewport is cleared automatically.

---

## 📂 File Output Structure

When saving:

```
input_folder/
├── image1.jpg
├── image2.png
└── ...
output/
├── image1.jpg          # Cropped JPEG
├── image1.txt          # Tag file (global words + per-image notes)
├── image2.jpg
├── image2.txt
└── ...
processed/
├── image1.jpg          # Original moved here
├── image2.png
└── ...
```

---

## 📝 Persistent Files

Created in the application directory:

- `config.json` — window geometry + last-used frame size.
- `global_words.txt` — your global tag list (always prefixed to `.txt` outputs).
- `suggest_history.txt` — alphabetical list of tags + their usage counts (for suggestions).

---

## ⌨️ Keyboard Shortcuts

- **Image movement**: Arrow keys (when canvas focused)
- **Zoom**: Mouse wheel; hold `Ctrl`/`⌘` for fine zoom
- **Fit image in frame**: `Fit full` button
- **Cover frame**: `Cover frame` button
- **Save & Next**: `Ctrl+S`
- **Fine zoom in/out**: `Ctrl`+`+`, `Ctrl`+`-`
- **Next image**: `Ctrl`+`Right`

---

## 🚀 Installation & Run

**Requirements**:
- Python 3.8+
- Pillow (PIL fork)

**Install dependencies**:
```bash
pip install pillow
```

**Run**:
```bash
python main.py
```

(`main.py` is the file containing the provided script.)

---

## 🖼️ Use Case

This tool is optimized for preparing image datasets where:
- Square crops are required.
- Each image needs an associated `.txt` metadata file containing tags.
- Tags can include global/common words and image-specific words.
- Duplicates are automatically removed.
- Image alignment should be pixel-perfect with zoom and snapping.

Originally designed for **LoRA training dataset prep**, but works well for any square-cropping workflow.

---

## 📌 Tips

- Use the **Global words** box for recurring tags like `keyword`, `solo`, `looking_at_viewer`.
- Adjust the frame size before starting to match your target training resolution.
- Keep an eye on the **suggestion buttons** — they save typing time for recurring tags.
- Resize the window freely — the image stays fixed relative to the frame.
