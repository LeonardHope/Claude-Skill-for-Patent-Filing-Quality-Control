"""Generate tiny sample filing PDFs for the v2 viewer + evidence tests.

Just enough real text to prove we can locate phrases (inventor surnames, the
title, the docket) and get their page + bounding box. Title/docket use the
generic BASE_ADS values from the test suite (no client data). Coordinates are
in points (unit="pt") so they line up directly with pdfplumber's output.

Run:  python3 app/sample/make_sample.py
"""
from pathlib import Path
from fpdf import FPDF

HERE = Path(__file__).resolve().parent
OUT = HERE / "Declaration.pdf"
TITLE = "MEMORY-EFFICIENT INFERENCE FOR LARGE LANGUAGE MODELS"
DOCKET = "LUM-0142US"


def build():
    pdf = FPDF(unit="pt", format="letter")  # 612 x 792 pt
    pdf.set_auto_page_break(False)

    # ---- Page 1: inventor 1 ----
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.set_xy(72, 90)
    pdf.cell(0, 18, "DECLARATION (37 CFR 1.63)")
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 130)
    pdf.cell(0, 14, "Attorney Docket Number: LUM-0142US")
    pdf.set_xy(72, 170)
    pdf.cell(0, 14, "I hereby declare that I am an original inventor of the claimed invention.")
    pdf.set_xy(72, 210)
    pdf.cell(0, 14, "Inventor 1")
    pdf.set_font("Helvetica", size=12)
    pdf.set_xy(72, 232)
    pdf.cell(0, 16, "Sarah J. CHEN")          # <-- locate target on page 1
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 260)
    pdf.cell(0, 14, "/Sarah J. Chen/    Date: 2026-05-09")

    # ---- Page 2: inventor 2 ----
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 90)
    pdf.cell(0, 14, "I hereby declare that I am an original inventor of the claimed invention.")
    pdf.set_xy(72, 130)
    pdf.cell(0, 14, "Inventor 2")
    pdf.set_font("Helvetica", size=12)
    pdf.set_xy(72, 152)
    pdf.cell(0, 16, "Aditya Vikram MEHTA")    # <-- locate target on page 2
    pdf.set_font("Helvetica", size=11)
    pdf.set_xy(72, 180)
    pdf.cell(0, 14, "/Aditya Vikram Mehta/    Date: 2026-05-09")

    pdf.output(str(OUT))
    print(f"wrote {OUT}")


def build_spec():
    """A small but realistically-structured specification: title, related-
    application/priority language, the standard section headers, numbered
    dependent claims, figure references, and an abstract — enough for the spec /
    claims / figure / priority checks to fire and attach receipts. Keeps the
    'BACKGROUND' header and the '[INSERT …]' placeholder that the tests locate."""
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(False)

    def line(x, y, text, size=11):
        pdf.set_font("Helvetica", size=size)
        pdf.set_xy(x, y)
        pdf.cell(0, 14, text)

    # ---- Page 1: front matter + description ----
    pdf.add_page()
    line(72, 90, TITLE, size=13)                              # title (Check 2)
    line(72, 122, "CROSS-REFERENCE TO RELATED APPLICATIONS")  # Checks 63/64
    line(72, 140, "This application claims the benefit of U.S. Provisional "
                  "Application No. 63/000,000, filed")
    line(72, 154, "January 5, 2025, which is incorporated herein by reference.")
    line(72, 184, "BACKGROUND")                               # Check 18 (+ receipt)
    line(72, 202, "Modern systems require efficient inference.")
    line(72, 216, "[INSERT DESCRIPTION OF PRIOR ART]")        # Check 50 (+ receipt)
    line(72, 246, "BRIEF DESCRIPTION OF THE DRAWINGS")        # Check 19 (+ receipt)
    line(72, 264, "FIG. 1 illustrates a system overview.")    # Checks 15/70
    line(72, 278, "FIG. 2 shows a method flow.")
    line(72, 308, "DETAILED DESCRIPTION")                     # Check 20 (+ receipt)
    line(72, 326, "Referring to FIG. 1, the system 100 includes a processor 110 "
                  "configured to")
    line(72, 340, "perform memory-efficient inference for large language models.")

    # ---- Page 2: claims + abstract ----
    pdf.add_page()
    line(72, 90, "What is claimed is:")                       # Check 21 (+ receipt)
    line(72, 116, "1. A method comprising: receiving input data; and processing "
                  "the input")
    line(72, 130, "data with a processor to produce an inference result.")
    line(72, 152, "2. The method of claim 1, further comprising storing the "
                  "inference result.")
    line(72, 174, "3. The method of claim 1, wherein processing comprises "
                  "quantized inference.")
    line(72, 214, "ABSTRACT")                                 # Check 17 (+ receipt)
    line(72, 232, "A method and system for memory-efficient inference for large "
                  "language")
    line(72, 246, "models, including a processor configured to process input "
                  "data and produce")
    line(72, 260, "an inference result.")

    out = HERE / "Specification.pdf"
    pdf.output(str(out)); print(f"wrote {out}")


def build_drawings():
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.set_xy(72, 54)
    pdf.cell(0, 14, f"(Docket No.: {DOCKET})")   # margin docket label (Check 23)
    pdf.set_xy(420, 54)
    pdf.cell(0, 14, "Sheet 1 of 1")
    pdf.set_font("Helvetica", size=12)
    pdf.set_xy(260, 380)
    pdf.cell(0, 16, "FIG. 1")
    out = HERE / "Drawings.pdf"
    pdf.output(str(out)); print(f"wrote {out}")


if __name__ == "__main__":
    build()
    build_spec()
    build_drawings()
