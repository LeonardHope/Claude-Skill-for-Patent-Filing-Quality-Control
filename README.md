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

### Recommended: Reduce Permission Prompts in Claude Code

By default Claude Code asks for permission on every Bash call, every PDF read, and every report write — running this skill on a real filing can trigger 50–100+ permission popups. To eliminate that without using `--dangerously-skip-permissions`, add the following to your `~/.claude/settings.json` (or your project's `.claude/settings.json`):

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 *qc_patent_filing.py*)",
      "Bash(pip install PyPDF2*)",
      "Bash(pip install fpdf2*)",
      "Bash(pip install pytesseract*)",
      "Bash(pip install pdf2image*)",
      "Bash(pdftotext *)",
      "Bash(pdfinfo *)",
      "Read(*.pdf)",
      "Write(*Patent_Filing_QC_Report*)"
    ]
  }
}
```

These rules cover the script invocation, dependency installs, the PDF reads the script and skill perform, and the two report files written to the filing folder. After adding them, a typical run will produce only a handful of permission prompts (or none, if everything is allowlisted).

## Usage

### Basic Usage

```bash
python3 scripts/qc_patent_filing.py /path/to/filing/documents
```

### With Custom Output Directory

```bash
python3 scripts/qc_patent_filing.py /path/to/filing/documents --output-dir /path/to/reports
```

### Optional: Authoritative Inventor List

If you drop any of these files into the filing folder, the script will use them as the canonical source of inventor names and run an additional cross-check (Check 71) against ADS / declaration / assignment / drawings:

| File | Format |
|------|--------|
| `inventors.json` | JSON array of `{"first", "middle", "last", "suffix"}` objects, or array of full-name strings |
| `inventors.txt`  | One inventor per line — `First Middle Last [Suffix]` or `Last, First M., Suffix` |
| `*.eml`          | Email file(s); names are extracted from the body on a best-effort basis |

This is useful for catching the case where a paralegal confirmed an inventor name in an email and the ADS form was filled in with a typo or missing middle name / suffix. Diacritic differences (e.g., `José` vs `Jose`, `Müller` vs `Muller`) are matched as equivalent so they don't cause false-positive failures.

Example `inventors.txt`:

```
Dharani Bharathi Thirupathi
Veerajothi Ramasamy
Sriram Santhanam
Smith, John P., Jr.
```

### Output

The script generates two report files:
- `Patent_Filing_QC_Report.md` - Markdown format for easy reading
- `Patent_Filing_QC_Report.pdf` - PDF format for distribution/archiving

## Quality Control Checks

### 1. Cross-Document Consistency (8 checks + 1 conditional)

Ensures information matches across all documents:

| Check | Description |
|-------|-------------|
| Inventor Names | Names match exactly across ADS, declaration, assignment, and drawings. SKIPPED entries explicitly list which sources were excluded (missing, unreadable, or no names extractable). |
| Application Title | Title is consistent across all documents |
| Attorney Docket Number | Docket number matches across all documents |
| Correspondence Address | Address aligns between ADS and other documents |
| Assignee Name | Assignee name is consistent where referenced |
| Filing Date Logic | Dates are logically consistent (no future dates, proper sequence) |
| Inventor Count | Number of inventors matches across documents |
| Citizenship/Residency | Inventor citizenship information is consistent |
| **Inventor Names vs. Authoritative Source** *(conditional)* | If `inventors.txt`, `inventors.json`, or `*.eml` is present, all documents are cross-checked against that list. Diacritic-tolerant matching. |

### 2. Document Completeness (4 checks)

Verifies all required components are present:

| Check | Description |
|-------|-------------|
| Required Documents Present | Specification, drawings, ADS, and declaration all exist |
| ADS Required Fields | All mandatory ADS fields are completed |
| Declaration Signatures | All inventors have signed the declaration |
| Assignment Signatures | All assignors have signed (if assignment included) |

**Missing-Parts Filings (37 CFR §1.53(f)):** If the Declaration is the only thing missing, the tool flags it as a CRITICAL with `ACTION REQUIRED: confirm whether intentional`. Claude will ask you whether you're filing without the declaration on purpose. If yes, the issue is downgraded to a warning and you're reminded that:

- A **§1.16(f) surcharge fee** is due at or after filing
- The missing parts must be filed within **2 months** of the USPTO's Notice to File Missing Parts to avoid abandonment

Missing Specification, Drawings, or ADS are *not* eligible for missing-parts treatment and remain CRITICAL.

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

### 5. ADS-Specific (5 + 2 conditional checks)

Validates the Application Data Sheet:

| Check | Description |
|-------|-------------|
| Complete Inventor Addresses | Full mailing address for each inventor |
| First Named Inventor | First inventor is clearly identified |
| Entity Status | Small/micro/large entity status is specified |
| Correspondence Address | Complete correspondence address provided |
| Attorney/Agent Registration | Valid registration numbers for practitioners |
| **Inventor Citizenship Populated** *(XFA only)* | All inventors have a citizenship dropdown populated. If blank for assignee-filers under 37 CFR 1.46, the warning notes that some practitioners intentionally leave this blank and capture citizenship in the Declaration — verify intent. |
| **Attorney vs. Correspondence Customer Number** *(XFA only)* | The two customer-number fields in the ADS (correspondence and attorney/agent) usually match. Warns on mismatch. |

When the ADS is read via XFA, the report also includes an **"ADS Data Summary (Extracted from XFA)"** table near the end showing all extracted fields (title, docket #, entity status, both customer numbers, assignee + address, drawing sheet count, representative figure, domestic continuity, foreign priority, non-publication request, AIA transition statement, signer, registration number, signature date, form pages) plus an inventor table with name / residency / city / country / citizenship.

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

### XFA-Based ADS Forms (USPTO PTO/AIA/14)
The USPTO web-fillable ADS is an XFA (Adobe LiveCycle) form. PyPDF2 and most PDF tools see only a "Please wait..." placeholder page when opening these forms — the actual filled-in data is stored in an embedded XML stream. **This script reads that XML stream directly**, so:

- ✅ No Adobe Acrobat Pro flattening is required
- ✅ No "Print to PDF" workaround needed
- ✅ Inventor first / middle / last names and the explicit suffix field (Jr., III, etc.) are read as separate structured values — far more reliable than regex extraction from OCR'd text, especially for foreign names with diacritics
- ✅ Works on any platform (no Adobe software needed at all)

When the script detects an XFA-based ADS, the console will show `✅ XFA extraction successful` and the cross-document checks will use the structured XFA data preferentially.

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
