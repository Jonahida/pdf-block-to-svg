# pdf-block-to-svg

**pdf-block-to-svg** is a Python GUI application that allows you to visually inspect a PDF, detect vector-drawn rectangular blocks, and export selected regions as **true SVG files** (not rasterized).

Unlike screenshot-based tools, this project works directly on the PDF’s vector drawing data, preserving exact geometry, paths, and colors.

---

# Project Status

## Work in progress — not fully functional yet

This project is under active development and is not yet production-ready.

The core GUI, PDF rendering, and rectangle detection logic are implemented, but:
- Some edge cases are not handled correctly
- SVG export may fail or produce incomplete results for complex PDFs
- APIs, behavior, and file structure may change

The repository is published for **experimentation, learning, and iteration**, not as a finished tool.

---

## Key Features

- Load any PDF and preview pages visually
- Zoom and pan with smooth interaction
- Automatically detect rectangular vector blocks from PDF drawings
- Handle nested rectangles and select the topmost (innermost) block
- Toggle block selection with a single click
- Export each selected block as a **pure SVG vector**
- No rasterization, no loss of quality

---

## How It Works (Core Logic)

1. **PDF Parsing**
   - Uses **PyMuPDF (fitz)** to load and inspect PDF pages
   - Vector drawings are extracted using `page.get_drawings()`

2. **Rectangle Detection**
   - Bounding boxes are collected from vector paths and rectangle primitives
   - Thin text outlines and extreme aspect ratios are filtered out
   - Near-duplicate rectangles are removed

3. **Interactive Selection**
   - Detected rectangles are overlaid on the PDF preview
   - Clicking selects the *smallest enclosing rectangle* (handles nesting)
   - Selected blocks are highlighted in real time

4. **SVG Export**
   - Only vector elements intersecting the selected block are exported
   - SVGs preserve:
     - Paths
     - Stroke width
     - Stroke and fill colors
   - Output is clean, editable SVG

---

## Main File

### `pdf_block_extractor_gui.py`

This is the **only required source file**.

Responsibilities:
- GUI (Tkinter)
- PDF rendering and zoom management
- Vector rectangle detection
- Block selection logic
- SVG generation and export

Entry point:
```bash
python pdf_block_extractor_gui.py
```
## Requirements

**Core Dependencies**
- Python 3.9+
- PyMuPDF – PDF parsing and vector extraction
- Pillow – Image rendering for preview
- Tkinter – GUI (included with most Python installs)

Install dependencies

```bash
pip install -r requirements.txt
```

**Minimal essential packages:**
- PyMuPDF
- Pillow
- numpy
- (Additional libraries in `requirements.txt` support SVG handling, geometry, and PDF processing.)

## Usage

1. Launch the application
2. Load a PDF file
3. Zoom and pan to inspect the page
4. Click **Detect Rectangles**
5. Click on blocks to select or deselect them
6. Click **Export Selected SVGs**
7. Choose an output folder

Each selected block is saved as a separate `.svg` file.

## Use Cases

- Extract vector icons or diagrams from PDFs
- Recover UI components from design PDFs
- Prepress and print workflows
- CAD / technical documentation reuse
- Converting boxed PDF drawings to editable SVGs

## Limitations
- Works on vector-drawn PDFs (not scanned images)
- Text converted to outlines may be ignored by design
- Currently exports from one page at a time

## License
MIT License