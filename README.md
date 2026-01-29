# Patent Filing Quality Control Skill

A comprehensive quality control tool for U.S. patent application filing documents. This Claude Code skill systematically checks for internal document errors, cross-document inconsistencies, USPTO compliance issues, and common filing mistakes before submission to the USPTO.

## Overview

Patent applications involve multiple interconnected documents where a single inconsistency—a misspelled inventor name, a mismatched docket number, or an incorrect figure reference—can cause delays, rejections, or legal complications. This skill automates the tedious but critical task of cross-checking all filing documents.

The skill performs **70+ automated checks** across all required and optional filing documents, generating detailed reports in both Markdown and PDF formats.

## Supported Documents

| Document | Required | Description |
|----------|----------|-------------|
| Specification | Yes | The patent application text including claims |
| Drawings | Yes | Figures and illustrations |
| Application Data Sheet (ADS) | Yes | Bibliographic information |
| Declaration | Yes | Inventor oath/declaration |
| Assignment | No | Transfer of rights to assignee |
| Power of Attorney | No | Authorization for practitioners |

## Installation

### Prerequisites

```bash
pip install PyPDF2 fpdf2 --break-system-packages
```

### Optional: OCR Support

For image-based PDFs (scanned documents):

```bash
pip install pytesseract pdf2image --break-system-packages
brew install tesseract poppler
```

## Usage

### Basic Usage

```bash
python3 scripts/qc_patent_filing.py /path/to/filing/documents
```

### With Custom Output Directory

```bash
python3 scripts/qc_patent_filing.py /path/to/filing/documents --output-dir /path/to/reports
```

### Output

The script generates two report files:
- `Patent_Filing_QC_Report.md` - Markdown format for easy reading
- `Patent_Filing_QC_Report.pdf` - PDF format for distribution/archiving

## Quality Control Checks

### 1. Cross-Document Consistency (8 checks)

Ensures information matches across all documents:

| Check | Description |
|-------|-------------|
| Inventor Names | Names match exactly across ADS, declaration, assignment, and drawings |
| Application Title | Title is consistent across all documents |
| Attorney Docket Number | Docket number matches across all documents |
| Correspondence Address | Address aligns between ADS and other documents |
| Assignee Name | Assignee name is consistent where referenced |
| Filing Date Logic | Dates are logically consistent (no future dates, proper sequence) |
| Inventor Count | Number of inventors matches across documents |
| Citizenship/Residency | Inventor citizenship information is consistent |

### 2. Document Completeness (4 checks)

Verifies all required components are present:

| Check | Description |
|-------|-------------|
| Required Documents Present | Specification, drawings, ADS, and declaration all exist |
| ADS Required Fields | All mandatory ADS fields are completed |
| Declaration Signatures | All inventors have signed the declaration |
| Assignment Signatures | All assignors have signed (if assignment included) |

### 3. Specification-Specific (15 checks)

Validates the patent specification document:

| Check | Description |
|-------|-------------|
| Sequential Claim Numbering | Claims are numbered 1, 2, 3... without gaps |
| Valid Claim Dependencies | Dependent claims reference existing claims |
| Figure References Match | All FIG. references correspond to actual drawings |
| Reference Numeral Consistency | Reference numbers used consistently throughout |
| Abstract Present | Abstract section exists |
| Abstract Length | Abstract is 150 words or fewer |
| Background Section | Background of the invention is present |
| Brief Description of Drawings | Brief description section exists |
| Detailed Description | Detailed description section is present |
| Claims Section | Claims are present and properly formatted |
| Claim Antecedent Basis | "Said" and "the" terms have prior antecedent |
| No Relative Terms | Avoids ambiguous terms like "about", "approximately" in claims |
| Proper Claim Format | Claims follow proper USPTO format |
| Independent Claim Structure | Independent claims are self-contained |
| Dependent Claim Structure | Dependent claims properly reference and add limitations |

### 4. Drawings-Specific (5 checks)

Validates the drawings/figures:

| Check | Description |
|-------|-------------|
| Sequential Figure Numbering | Figures are numbered FIG. 1, FIG. 2... without gaps |
| Figure Labels Present | All figures have proper labels |
| Sheet Numbering | Sheets are numbered X/Y format |
| Black and White Compliance | Drawings are black and white (or color petition noted) |
| Legibility | Text and lines are clear and readable |

### 5. ADS-Specific (5 checks)

Validates the Application Data Sheet:

| Check | Description |
|-------|-------------|
| Complete Inventor Addresses | Full mailing address for each inventor |
| First Named Inventor | First inventor is clearly identified |
| Entity Status | Small/micro/large entity status is specified |
| Correspondence Address | Complete correspondence address provided |
| Attorney/Agent Registration | Valid registration numbers for practitioners |

### 6. Declaration-Specific (4 checks)

Validates the inventor declaration:

| Check | Description |
|-------|-------------|
| All Inventors Named | Every inventor from ADS is on declaration |
| Oath vs Declaration Format | Proper format is used consistently |
| Application Reference | Declaration references correct application |
| Execution Date | Date is logical (not future, not too old) |

### 7. Assignment-Specific (5 checks)

Validates the assignment document (if present):

| Check | Description |
|-------|-------------|
| All Assignors Identified | All inventors listed as assignors |
| Assignee Named | Assignee entity is clearly identified |
| Application Reference | References correct application/docket number |
| Execution Date | Date is logical and properly formatted |
| Rights Transfer Language | Proper legal language for assignment |

### 8. Power of Attorney-Specific (4 checks)

Validates the POA document (if present):

| Check | Description |
|-------|-------------|
| Practitioners Listed | All attorneys/agents are named |
| Registration Numbers | USPTO registration numbers included |
| Address Match | Address matches ADS correspondence address |
| Proper Signatures | Required signatures are present |

### 9. USPTO Formatting Compliance (5 checks)

Validates formatting requirements:

| Check | Description |
|-------|-------------|
| Line Numbering | Lines numbered every 5 lines in specification |
| Margin Compliance | Margins meet USPTO requirements (top: 2cm, left: 2.5cm, right: 2cm, bottom: 2cm) |
| Font Size | Text is at least 12 point |
| Double Spacing | Specification is double-spaced |
| Page Numbering | Pages are numbered consecutively |

### 10. Common Error Detection (5 checks)

Catches frequent mistakes:

| Check | Description |
|-------|-------------|
| No Placeholder Text | No [INSERT], TODO, XXX, TBD, or similar placeholders |
| No Track Changes | No visible revision marks or comments |
| Consistent Terminology | Same terms used consistently in claims |
| Antecedent Basis | All claim terms have proper antecedent basis |
| Terms Defined | Technical terms in claims are defined in specification |

### 11. File Quality (4 checks)

Validates PDF file properties:

| Check | Description |
|-------|-------------|
| Text-Searchable | PDFs contain extractable text (not just images) |
| Logical File Naming | Files have descriptive, consistent names |
| No Password Protection | PDFs are not password protected |
| Reasonable File Size | Files are not suspiciously large or small |

### 12. Cross-Reference Validation (4 checks)

Ensures internal references are valid:

| Check | Description |
|-------|-------------|
| Claims Reference Specification | Claim elements appear in specification |
| Summary Matches Claims | Summary scope aligns with claims |
| Figure Count Consistency | Number of figures matches references |
| Claim Count Verification | Claim count matches across documents |

### 13. Priority/Related Applications (3 checks)

Validates priority claims:

| Check | Description |
|-------|-------------|
| Priority Claim Consistency | Priority info matches across documents |
| Related Application References | Related apps referenced consistently |
| Foreign Priority Documentation | Foreign priority properly documented |

### 14. Final Quality (5 checks)

Final review checks:

| Check | Description |
|-------|-------------|
| No Obvious Typos | Critical fields free of typos |
| Dates Properly Formatted | All dates in correct format |
| Claim Length | No excessively long claims (readability) |
| Specification Support | All claim limitations supported in spec |
| Figure Reference Format | Consistent FIG. vs Figure usage |

## Report Severity Levels

Each check produces one of these results:

| Level | Icon | Meaning |
|-------|------|---------|
| PASS | ✅ | Check passed, no action needed |
| WARNING | ⚠️ | Potential issue, review recommended |
| CRITICAL | 🚨 | Must fix before filing |
| LOW CONFIDENCE | ❓ | Possible issue, manual verification needed |
| INFO | ℹ️ | Manual review recommended |

## Known Limitations

### PDF Text Extraction
PDF text extraction can sometimes merge words across line breaks. The tool is designed to avoid false positives from extraction artifacts, but some edge cases may occur.

### Patent Drafting Conventions
The tool recognizes common patent drafting conventions (e.g., sentences beginning with subordinate conjunctions) and avoids flagging these as errors.

### Form Field Reading
When reading fillable forms (like ADS), form field boundaries can affect text extraction. The tool cross-references multiple documents to avoid false positives.

### What This Tool Cannot Do
- Replace human judgment on legal/technical issues
- Evaluate claim scope adequacy
- Assess patentability
- Verify technical accuracy of the invention description

## Best Practices

1. **Run QC multiple times** - After each round of fixes, re-run to catch new issues
2. **Don't ignore INFO items** - These require manual verification
3. **Fix critical issues first** - These will cause filing rejections
4. **Investigate warnings** - May be false positives, but often indicate real problems
5. **Keep both reports** - Archive with filing records
6. **Human review is essential** - Automated checks supplement but don't replace attorney review

## File Structure

```
patent-filing-qc/
├── SKILL.md              # Claude Code skill definition
├── README.md             # This file
└── scripts/
    └── qc_patent_filing.py   # Main QC script
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
