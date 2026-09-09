"""Extract text and images from the snapshot PDF."""
import sys
import fitz  # PyMuPDF

doc = fitz.open(r"C:\Users\WIN\Documents\snapshot-letter-live.pdf")
print(f"Pages: {len(doc)}")
print(f"Metadata: {doc.metadata}")

for i, page in enumerate(doc):
    print(f"\n{'='*70}")
    print(f"PAGE {i+1} (size: {page.rect.width}x{page.rect.height})")
    print(f"{'='*70}")
    text = page.get_text()
    print(text)
    # Extract images
    images = page.get_images(full=True)
    if images:
        print(f"\n--- {len(images)} image(s) on this page ---")
        for j, img in enumerate(images):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha > 3:  # CMYK
                pix = fitz.Pixmap(fitz.csRGB, pix)
            out = rf"C:\Users\WIN\Documents\pdf_page{i+1}_img{j+1}.png"
            pix.save(out)
            print(f"  Saved: {out} ({pix.width}x{pix.height})")

doc.close()
