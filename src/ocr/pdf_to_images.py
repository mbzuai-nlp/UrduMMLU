#!/usr/bin/env python3
import sys
from pathlib import Path

import fitz  # PyMuPDF


def pdf_to_images(pdf_path: str, dpi: int = 300) -> Path:
    pdf_file = Path(pdf_path).expanduser().resolve()

    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_file}")
    if pdf_file.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {pdf_file}")

    output_dir = pdf_file.parent / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_file)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        out_file = output_dir / f"{pdf_file.stem}_page_{page_num + 1}.png"
        pix.save(out_file)

    doc.close()
    return output_dir


def main():
    if len(sys.argv) != 2:
        print("Usage: python pdf_to_images.py /path/to/file.pdf")
        sys.exit(1)

    try:
        output_dir = pdf_to_images(sys.argv[1])
        print(f"Images saved in: {output_dir}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()