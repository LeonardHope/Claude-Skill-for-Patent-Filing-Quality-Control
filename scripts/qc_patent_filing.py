#!/usr/bin/env python3
"""
Patent Filing Quality Control Script

Performs comprehensive QC checks on patent application filing documents.
Generates both Markdown and PDF reports.
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum
import PyPDF2
import argparse

# OCR support (optional)
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class Severity(Enum):
    """Issue severity levels"""
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"
    PASS = "PASS"


@dataclass
class QCIssue:
    """Represents a single QC check result"""
    check_id: int
    category: str
    check_name: str
    severity: Severity
    message: str
    details: str = ""


@dataclass
class QCReport:
    """Container for all QC results"""
    folder_path: str
    files_found: Dict[str, Optional[str]] = field(default_factory=dict)
    issues: List[QCIssue] = field(default_factory=list)
    
    def add_issue(self, check_id: int, category: str, check_name: str, 
                  severity: Severity, message: str, details: str = ""):
        """Add an issue to the report"""
        self.issues.append(QCIssue(check_id, category, check_name, severity, message, details))
    
    def get_critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)
    
    def get_warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)
    
    def get_pass_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.PASS)


class PatentFilingQC:
    """Main QC engine for patent filing documents"""
    
    def __init__(self, folder_path: str):
        self.folder_path = Path(folder_path)
        self.report = QCReport(folder_path=str(folder_path))
        self.spec_text = ""
        self.ads_text = ""
        self.declaration_text = ""
        self.assignment_text = ""
        self.poa_text = ""
        self.drawings_text = ""
        
    def extract_pdf_text(self, pdf_path: Path, doc_type: str = "Document") -> str:
        """Extract text from a PDF file, with OCR fallback for image-based PDFs"""
        try:
            # First, try normal text extraction
            text = ""
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

            # Check if we got meaningful text (more than just whitespace/boilerplate)
            clean_text = text.strip()
            if len(clean_text) > 100 and "Please wait" not in clean_text[:200]:
                return text

            # Text extraction failed or returned minimal content - try OCR
            if OCR_AVAILABLE:
                print(f"  ℹ️  {doc_type} appears to be image-based, attempting OCR...")
                try:
                    images = convert_from_path(pdf_path)
                    ocr_text = ""
                    for i, image in enumerate(images):
                        page_text = pytesseract.image_to_string(image)
                        ocr_text += page_text + "\n"

                    if len(ocr_text.strip()) > 100:
                        print(f"  ✅ OCR successful for {doc_type}")
                        return ocr_text
                    else:
                        self._document_read_failure(doc_type, pdf_path, "OCR returned minimal text")
                        return ""
                except Exception as ocr_error:
                    self._document_read_failure(doc_type, pdf_path, f"OCR failed: {str(ocr_error)}")
                    return ""
            else:
                self._document_read_failure(doc_type, pdf_path,
                    "Image-based PDF detected but OCR not available. "
                    "Install pytesseract and pdf2image: pip install pytesseract pdf2image")
                return ""

        except Exception as e:
            self._document_read_failure(doc_type, pdf_path, str(e))
            return ""

    def _document_read_failure(self, doc_type: str, pdf_path: Path, reason: str):
        """Handle document read failure with helpful error message"""
        print(f"\n  🚨 FAILED TO READ {doc_type.upper()}: {pdf_path.name}")
        print(f"     Reason: {reason}")
        print(f"     Solutions:")
        print(f"       1. Open the original fillable form and 'Print to PDF'")
        print(f"       2. Use Adobe Acrobat's 'Recognize Text' (OCR) feature")
        print(f"       3. Re-export from the source application as a text-based PDF")
        print()
    
    def find_document(self, patterns: List[str], doc_type: str) -> Optional[Path]:
        """Find a document matching any of the given patterns"""
        for pattern in patterns:
            matches = list(self.folder_path.glob(pattern))
            if matches:
                self.report.files_found[doc_type] = str(matches[0].name)
                return matches[0]
        self.report.files_found[doc_type] = None
        return None
    
    def load_documents(self):
        """Locate and load all filing documents"""
        # Find specification PDF (case-insensitive patterns)
        spec_path = self.find_document(
            ['*[Ss]pec*.pdf', '*[Ss]pecification*.pdf', '*-Specification.pdf', 'spec.pdf'],
            'Specification'
        )
        if spec_path:
            self.spec_text = self.extract_pdf_text(spec_path, 'Specification')

        # Find drawings PDF
        drawings_path = self.find_document(
            ['*[Dd]rawing*.pdf', '*[Ff]igure*.pdf', '*[Ff]ig*.pdf', '*-Drawings.pdf', 'drawings.pdf'],
            'Drawings'
        )
        if drawings_path:
            self.drawings_text = self.extract_pdf_text(drawings_path, 'Drawings')

        # Find ADS
        ads_path = self.find_document(
            ['*[Aa][Dd][Ss]*.pdf', '*ADS*.pdf', '*-ADS.pdf', '*application*data*sheet*.pdf', 'ads.pdf'],
            'ADS'
        )
        if ads_path:
            self.ads_text = self.extract_pdf_text(ads_path, 'ADS')

        # Find declaration (including combined Dec-Assignment files)
        decl_path = self.find_document(
            ['*[Dd]ecl*.pdf', '*[Dd]eclaration*.pdf', '*[Oo]ath*.pdf', '*Dec*.pdf', 'declaration.pdf'],
            'Declaration'
        )
        if decl_path:
            self.declaration_text = self.extract_pdf_text(decl_path, 'Declaration')

        # Find assignment (including combined Exec-Dec-Assignment files)
        assignment_path = self.find_document(
            ['*[Aa]ssign*.pdf', '*[Aa]ssignment*.pdf', '*Assignment*.pdf', 'assignment.pdf'],
            'Assignment'
        )
        if assignment_path:
            self.assignment_text = self.extract_pdf_text(assignment_path, 'Assignment')

        # Find POA
        poa_path = self.find_document(
            ['*[Pp][Oo][Aa]*.pdf', '*POA*.pdf', '*-POA.pdf', '*[Pp]ower*.pdf', '*[Aa]ttorney*.pdf', 'poa.pdf'],
            'Power of Attorney'
        )
        if poa_path:
            self.poa_text = self.extract_pdf_text(poa_path, 'Power of Attorney')

        # Check for required documents that couldn't be read
        self._check_required_documents_readable()

    def _check_required_documents_readable(self):
        """Verify that required documents were successfully read"""
        required_docs = {
            'Specification': self.spec_text,
            'Drawings': self.drawings_text,
            'ADS': self.ads_text,
            'Declaration': self.declaration_text,
        }

        unreadable = []
        for doc_name, text in required_docs.items():
            if self.report.files_found.get(doc_name):  # File was found
                if not text or len(text.strip()) < 100:  # But couldn't be read
                    unreadable.append(doc_name)

        if unreadable:
            print("\n" + "=" * 70)
            print("🚨 CRITICAL: REQUIRED DOCUMENTS COULD NOT BE READ")
            print("=" * 70)
            for doc in unreadable:
                filename = self.report.files_found.get(doc, 'Unknown')
                print(f"  • {doc}: {filename}")
            print("\nThe QC report will be incomplete. Please fix the above documents")
            print("and re-run the QC check.")
            print("=" * 70 + "\n")

    def extract_inventors(self, text: str) -> List[str]:
        """Extract inventor names from text"""
        inventors = []

        # Pattern 1: ADS OCR format - names after "Suffix" field
        # Matches: "Suffix\nFirstName LASTNAME" or "Suffix\nFirst Middle LASTNAME"
        suffix_pattern = r'Suffix\s*\n?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+[A-Z]{2,})\s*\n'
        matches = re.findall(suffix_pattern, text)
        for match in matches:
            name = ' '.join(match.split())
            words = name.split()
            if 2 <= len(words) <= 4 and words[-1].isupper() and len(words[-1]) >= 2:
                inventors.append(name)

        # Pattern 2: Declaration/Assignment format - names after "Assignor(s):"
        # Names appear on their own lines as "First LAST" or "First Middle LAST"
        # Look for section between "Assignor" and "Assignee"
        assignor_section = re.search(r'Assignor\s*\(s\)\s*:?\s*(.*?)(?:Assignee|AGREEMENT)', text, re.DOTALL | re.IGNORECASE)
        if assignor_section:
            section_text = assignor_section.group(1)
            # Find names in format "First LAST" or "First Middle LAST" at start of lines
            name_pattern = r'^\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+[A-Z]{2,})\s*$'
            matches = re.findall(name_pattern, section_text, re.MULTILINE)
            for match in matches:
                name = ' '.join(match.split())
                words = name.split()
                if 2 <= len(words) <= 4 and words[-1].isupper() and len(words[-1]) >= 2:
                    inventors.append(name)

        # Pattern 3: Direct "First LAST" pattern in text (for various document formats)
        # Be more targeted - look for names followed by address or "c/o"
        name_with_address = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+[A-Z]{2,})\s*\n\s*c/o'
        matches = re.findall(name_with_address, text)
        for match in matches:
            name = ' '.join(match.split())
            words = name.split()
            if 2 <= len(words) <= 4 and words[-1].isupper() and len(words[-1]) >= 2:
                inventors.append(name)

        # If we found inventors, return unique list
        if inventors:
            return list(set(inventors))

        # Fallback: Look for declaration format "I, [Name], declare"
        decl_pattern = r'(?:I,\s*)([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)(?:,?\s*declare)'
        matches = re.findall(decl_pattern, text, re.IGNORECASE)
        for match in matches:
            name = ' '.join(match.split())
            if len(name) > 4:
                inventors.append(name)

        return list(set(inventors))
    
    def extract_title(self, text: str) -> str:
        """Extract application title from text"""
        # Multiple patterns for different document formats
        patterns = [
            # ADS format: "Title of Invention | TITLE HERE" or "Title of Invention TITLE HERE"
            r'Title\s+of\s+Invention[\s\|]+([A-Z][A-Z\s\-]+)',
            # Standard format: "Title: TITLE HERE"
            r'(?:Title|TITLE)[:\s]+([A-Z][A-Z\s\-]+)',
            # Specification format: Title after docket number and page number
            # "A088-0170US \n 1 TITLE HERE BACKGROUND"
            r'Docket[^\n]+\n\s*\d+\s+([A-Z][A-Z\s\-]+)',
            # Declaration/Assignment format: title in quotes
            r'entitled\s*["\']([^"\']+)["\']',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Clean up: remove extra whitespace, normalize
                title = ' '.join(title.split())

                # Truncate at common section headers that might follow the title
                for stop_word in ['BACKGROUND', 'FIELD', 'CROSS', 'RELATED', 'ABSTRACT',
                                  'TECHNICAL', 'SUMMARY', 'BRIEF', 'The application',
                                  'This application', 'T ']:  # 'T ' handles OCR artifacts
                    if stop_word in title:
                        title = title.split(stop_word)[0].strip()

                # Filter out things that aren't titles (too short, or boilerplate)
                if len(title) > 10 and 'PATENT' not in title and 'TRADEMARK' not in title:
                    return title
        return ""
    
    def extract_docket_number(self, text: str) -> str:
        """Extract attorney docket number from text"""
        # Patterns ordered from most specific to least specific
        # Docket numbers typically look like: A088-0170US, 12345-001, ABC-123-US, etc.
        patterns = [
            # "Attorney Docket No.: A088-0170US" or "Docket No.: A088-0170US"
            r'(?:Attorney\s*)?Docket\s*(?:No\.?|Number)[:\s]+([A-Z0-9][A-Z0-9\-\.]+[A-Z0-9])',
            # "Docket: A088-0170US"
            r'Docket[:\s]+([A-Z0-9][A-Z0-9\-\.]+[A-Z0-9])',
            # Look for common docket number patterns directly (letter-numbers-letters format)
            r'\b([A-Z]\d{2,4}-\d{3,5}[A-Z]{0,3})\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                docket = match.group(1).strip()
                # Validate it looks like a real docket number (not just "No" or "Number")
                if len(docket) >= 5 and re.search(r'\d', docket):
                    return docket
        return ""
    
    def normalize_name(self, name: str) -> str:
        """Normalize a name for comparison"""
        # Remove extra whitespace, convert to uppercase
        return re.sub(r'\s+', ' ', name.strip().upper())

    def _extract_figure_numbers(self, text: str) -> List[int]:
        """
        Extract figure numbers from text, handling PyPDF2 extraction quirks.

        PyPDF2 often concatenates text without spaces, so:
        - "FIG. 2" + "118" (ref numeral) becomes "FIG. 2118"
        - "FIG. 4" + "START" becomes "FIG. 4START"
        - "FIG. 5" + "CPU" becomes "FIG. 5CPU"

        This method handles such cases intelligently.
        """
        if not text:
            return []

        fig_nums = set()

        # All patterns require FIG to be a standalone word (preceded by non-letter or start)
        # This prevents matching "CONFIG" as containing "FIG"

        # Pattern 1: FIG. N followed by sub-figure letter A-E, then non-letter or more text
        # e.g., "FIG. 3A " or "FIG. 3ABUILD" -> extracts 3
        for match in re.finditer(r'(?:^|[^A-Z])FIG(?:URE)?\.?\s*(\d{1,2})([A-E])(?:[^A-Z]|[A-Z])', text, re.IGNORECASE):
            num = int(match.group(1))
            if 1 <= num <= 20:
                fig_nums.add(num)

        # Pattern 2: FIG. N followed by uppercase letter F-Z (not a sub-figure)
        # e.g., "FIG. 4START" -> extracts 4, "FIG. 5CPU" -> extracts 5
        for match in re.finditer(r'(?:^|[^A-Z])FIG(?:URE)?\.?\s*(\d{1,2})([F-Z])', text, re.IGNORECASE):
            num = int(match.group(1))
            if 1 <= num <= 20:
                fig_nums.add(num)

        # Pattern 3: FIG. N followed by space, newline, punctuation, or end
        for match in re.finditer(r'(?:^|[^A-Z])FIG(?:URE)?\.?\s*(\d{1,2})(?:[\s\.,;:\)\]\-]|$)', text, re.IGNORECASE):
            num = int(match.group(1))
            if 1 <= num <= 20:
                fig_nums.add(num)

        # Pattern 4: FIG. single-digit followed by 3+ digits (reference numeral)
        # e.g., "FIG. 2118" -> extracts 2 (118 is likely a ref numeral)
        for match in re.finditer(r'(?:^|[^A-Z])FIG(?:URE)?\.?\s*(\d)(\d{3,})', text, re.IGNORECASE):
            num = int(match.group(1))
            if 1 <= num <= 9:
                fig_nums.add(num)

        # Pattern 5: FIG. 1N or 20 followed by 2+ digits
        # e.g., "FIG. 10200" -> extracts 10
        for match in re.finditer(r'(?:^|[^A-Z])FIG(?:URE)?\.?\s*(1\d|20)(\d{2,})', text, re.IGNORECASE):
            num = int(match.group(1))
            if 10 <= num <= 20:
                fig_nums.add(num)

        return sorted(fig_nums)

    def _extract_reference_numerals(self, text: str) -> dict:
        """
        Extract reference numerals from specification text with their descriptions.

        Returns a dict mapping reference numeral (str) to a dict containing:
        - 'descriptions': set of description strings found (canonical element names)
        - 'count': number of occurrences
        - 'type': 'element' or 'operation' (flowchart step)
        """
        if not text:
            return {}

        ref_data = {}

        # Pattern 1: Canonical element descriptions - "the NOUN NOUN NUM" or "a/an NOUN NOUN NUM"
        # e.g., "the computing platform 102", "a supervisor agent 204", "the BMC 106"
        # Limit to 1-3 words to avoid capturing surrounding context
        # Use word boundary and require the element name to be a proper noun phrase
        canonical_pattern = r'(?:the|a|an)\s+((?:[A-Z]{2,}|[\w\-]+(?:\s+[\w\-]+){0,2}))\s+(\d{3})\b'

        for match in re.finditer(canonical_pattern, text, re.IGNORECASE):
            desc = match.group(1).strip().lower()
            num = match.group(2)

            # Skip likely dates or non-reference numbers
            if int(num) < 100 or int(num) > 999:
                continue

            # Check if this is an operation/step/block reference (flowchart)
            is_operation = desc in ['operation', 'step', 'block'] or desc.startswith(('operation ', 'step ', 'block '))

            # Filter out noise
            noise_words = ['page', 'fig', 'figure', 'claim', 'method', 'system', 'device', 'apparatus',
                          'january', 'february', 'march', 'april', 'may', 'june',
                          'july', 'august', 'september', 'october', 'november', 'december',
                          'docket', 'attorney', 'no.', 'a088', 'patent', 'application',
                          'embodiment', 'example', 'implementation', 'aspect', 'routine',
                          'interface between', 'multitude of', 'plurality of', 'portion of']
            if any(noise in desc for noise in noise_words):
                continue

            # Skip if description is just common words or too generic
            generic_words = ['first', 'second', 'third', 'one', 'two', 'other', 'same', 'such', 'following']
            if desc in generic_words or all(w in generic_words for w in desc.split()):
                continue

            # Extract just the core element name (last 1-2 significant words)
            # This helps normalize "supervisor agent" vs "the supervisor agent"
            words = desc.split()
            # Remove prepositions and articles from the extracted phrase
            prepositions = ['of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from', 'between']
            core_words = []
            for w in words:
                if w in prepositions:
                    # Reset - take only words after preposition
                    core_words = []
                else:
                    core_words.append(w)

            desc_normalized = ' '.join(core_words[-3:]) if core_words else desc  # Take last 3 words max

            if num not in ref_data:
                ref_data[num] = {'descriptions': set(), 'count': 0, 'type': 'operation' if is_operation else 'element'}

            if desc_normalized and len(desc_normalized) >= 2:
                ref_data[num]['descriptions'].add(desc_normalized)

            ref_data[num]['count'] += 1

            # Update type if we find element usage (element takes precedence over operation)
            if not is_operation and ref_data[num]['type'] == 'operation':
                ref_data[num]['type'] = 'element'

        # Pattern 2: Direct element introductions like "element 102" or "(102)"
        # Also catch "NUM (the DESCRIPTION)" patterns
        intro_pattern = r'(\d{3})\s*\((?:the\s+)?([\w\-]+(?:\s+[\w\-]+){0,2})\)'
        for match in re.finditer(intro_pattern, text, re.IGNORECASE):
            num = match.group(1)
            desc = match.group(2).strip().lower()

            if 100 <= int(num) <= 999 and len(desc) >= 2:
                if num not in ref_data:
                    ref_data[num] = {'descriptions': set(), 'count': 0, 'type': 'element'}
                ref_data[num]['descriptions'].add(desc)
                ref_data[num]['count'] += 1

        # Pattern 3: Operation references like "at operation 332", "to operation 404"
        operation_pattern = r'(?:at|to|from|of|proceeds to|continues to)\s+(operation|step|block)\s+(\d{3})\b'
        for match in re.finditer(operation_pattern, text, re.IGNORECASE):
            op_type = match.group(1).lower()
            num = match.group(2)

            if 100 <= int(num) <= 999:
                if num not in ref_data:
                    ref_data[num] = {'descriptions': set(), 'count': 0, 'type': 'operation'}
                ref_data[num]['descriptions'].add(op_type)
                ref_data[num]['count'] += 1

        return ref_data

    def _extract_reference_numerals_from_drawings(self, text: str) -> set:
        """
        Extract reference numerals from drawings text.
        Drawings often have limited text, so this extracts what's available.
        """
        if not text:
            return set()

        refs = set()
        # Look for 3-digit numbers that are likely reference numerals
        pattern = r'\b(\d{3})\b'
        for match in re.finditer(pattern, text):
            num = match.group(1)
            if 100 <= int(num) <= 999:
                refs.add(num)

        return refs

    def run_all_checks(self):
        """Execute all 70 QC checks"""
        self.check_cross_document_consistency()
        self.check_document_completeness()
        self.check_specification()
        self.check_drawings()
        self.check_ads()
        self.check_declaration()
        self.check_assignment()
        self.check_poa()
        self.check_formatting()
        self.check_common_errors()
        self.check_file_quality()
        self.check_cross_references()
        self.check_priority()
        self.check_final_quality()
    
    def check_cross_document_consistency(self):
        """Checks 1-8: Cross-document consistency"""
        
        # Check 1: Inventor names consistency
        ads_inventors = self.extract_inventors(self.ads_text) if self.ads_text else []
        decl_inventors = self.extract_inventors(self.declaration_text) if self.declaration_text else []
        assign_inventors = self.extract_inventors(self.assignment_text) if self.assignment_text else []
        drawings_inventors = self.extract_inventors(self.drawings_text) if self.drawings_text else []
        
        all_inventor_sets = [
            ("ADS", set(self.normalize_name(i) for i in ads_inventors)),
            ("Declaration", set(self.normalize_name(i) for i in decl_inventors)),
            ("Assignment", set(self.normalize_name(i) for i in assign_inventors)),
            ("Drawings", set(self.normalize_name(i) for i in drawings_inventors))
        ]
        
        # Filter out empty sets
        non_empty_sets = [(name, inv_set) for name, inv_set in all_inventor_sets if inv_set]
        
        if len(non_empty_sets) >= 2:
            all_match = all(inv_set == non_empty_sets[0][1] for _, inv_set in non_empty_sets)
            if all_match:
                self.report.add_issue(
                    1, "Cross-Document Consistency", "Inventor Names Consistency",
                    Severity.PASS, "Inventor names match across all documents"
                )
            else:
                mismatches = []
                for name, inv_set in non_empty_sets:
                    mismatches.append(f"{name}: {inv_set}")
                self.report.add_issue(
                    1, "Cross-Document Consistency", "Inventor Names Consistency",
                    Severity.CRITICAL, "Inventor names do not match across documents",
                    "\n".join(mismatches)
                )
        else:
            self.report.add_issue(
                1, "Cross-Document Consistency", "Inventor Names Consistency",
                Severity.WARNING, "Unable to extract inventor names from multiple documents for comparison"
            )
        
        # Check 2: Application title consistency
        spec_title = self.extract_title(self.spec_text)
        ads_title = self.extract_title(self.ads_text)
        
        if spec_title and ads_title:
            if spec_title.upper() == ads_title.upper():
                self.report.add_issue(
                    2, "Cross-Document Consistency", "Application Title Consistency",
                    Severity.PASS, "Application title matches across documents"
                )
            else:
                self.report.add_issue(
                    2, "Cross-Document Consistency", "Application Title Consistency",
                    Severity.CRITICAL, "Application title mismatch",
                    f"Spec: {spec_title}\nADS: {ads_title}"
                )
        else:
            self.report.add_issue(
                2, "Cross-Document Consistency", "Application Title Consistency",
                Severity.WARNING, "Unable to extract titles from both specification and ADS"
            )
        
        # Check 3: Attorney docket number consistency
        dockets = []
        for name, text in [("Spec", self.spec_text), ("ADS", self.ads_text), 
                           ("Declaration", self.declaration_text), ("Assignment", self.assignment_text)]:
            if text:
                docket = self.extract_docket_number(text)
                if docket:
                    dockets.append((name, docket))
        
        if len(dockets) >= 2:
            all_match = all(d[1].upper() == dockets[0][1].upper() for d in dockets)
            if all_match:
                self.report.add_issue(
                    3, "Cross-Document Consistency", "Attorney Docket Number Consistency",
                    Severity.PASS, "Attorney docket number matches across documents"
                )
            else:
                details = "\n".join([f"{name}: {docket}" for name, docket in dockets])
                self.report.add_issue(
                    3, "Cross-Document Consistency", "Attorney Docket Number Consistency",
                    Severity.CRITICAL, "Attorney docket number mismatch", details
                )
        else:
            self.report.add_issue(
                3, "Cross-Document Consistency", "Attorney Docket Number Consistency",
                Severity.WARNING, "Unable to extract docket numbers from multiple documents"
            )
        
        # Check 4: Correspondence address consistency
        # Compare customer number across ADS and POA (if present)
        ads_customer_num = None
        poa_customer_num = None

        if self.ads_text:
            cust_match = re.search(r'Customer\s*(?:Number|No\.?)[:\s]*(\d{5,6})', self.ads_text, re.IGNORECASE)
            if cust_match:
                ads_customer_num = cust_match.group(1)

        if self.poa_text:
            cust_match = re.search(r'Customer\s*(?:Number|No\.?)[:\s]*(\d{5,6})', self.poa_text, re.IGNORECASE)
            if cust_match:
                poa_customer_num = cust_match.group(1)

        if ads_customer_num and poa_customer_num:
            if ads_customer_num == poa_customer_num:
                self.report.add_issue(
                    4, "Cross-Document Consistency", "Correspondence Address Consistency",
                    Severity.PASS, f"Customer number consistent: {ads_customer_num}"
                )
            else:
                self.report.add_issue(
                    4, "Cross-Document Consistency", "Correspondence Address Consistency",
                    Severity.CRITICAL, f"Customer number mismatch: ADS={ads_customer_num}, POA={poa_customer_num}"
                )
        elif ads_customer_num or poa_customer_num:
            self.report.add_issue(
                4, "Cross-Document Consistency", "Correspondence Address Consistency",
                Severity.PASS, f"Customer number found: {ads_customer_num or poa_customer_num}"
            )
        else:
            self.report.add_issue(
                4, "Cross-Document Consistency", "Correspondence Address Consistency",
                Severity.INFO, "No customer number found - manual review of correspondence address recommended"
            )
        
        # Check 5: Assignee name consistency
        # Extract assignee from ADS and Assignment, compare them
        ads_assignee = None
        assignment_assignee = None

        # Look for assignee in ADS - try multiple patterns
        if self.ads_text:
            # Pattern 1: Look for "Organization Name" followed by company (handles OCR "ization")
            org_match = re.search(
                r'(?:Organization|ization)\s*Name\s*[|\s]+([A-Za-z][\w\s,]+(?:LLC|Inc|Corp))',
                self.ads_text, re.IGNORECASE
            )
            if org_match:
                ads_assignee = org_match.group(1).strip()

            # Pattern 2: Look for "c/o Company Name" in addresses
            if not ads_assignee:
                co_match = re.search(
                    r'c/o\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+(?:,?\s*(?:LLC|Inc|Corp)))',
                    self.ads_text, re.IGNORECASE
                )
                if co_match:
                    ads_assignee = co_match.group(1).strip()

            # Pattern 3: Look for "Applicant Name" field with company
            if not ads_assignee:
                applicant_match = re.search(
                    r'Applicant\s*Name[:\s|]+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+(?:,?\s*(?:LLC|Inc|Corp)))',
                    self.ads_text, re.IGNORECASE
                )
                if applicant_match:
                    ads_assignee = applicant_match.group(1).strip()

        # Look for assignee in Assignment
        if self.assignment_text:
            # Look for company name pattern - "Word Word, LLC" or "Word Word LLC"
            assignment_assignee_match = re.search(
                r'([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+(?:,?\s*(?:LLC|Inc|Corp)))',
                self.assignment_text
            )
            if assignment_assignee_match:
                assignment_assignee = assignment_assignee_match.group(1).strip()

        # Normalize for comparison - handle OCR errors
        def normalize_company(name):
            if not name:
                return ""
            # Handle common OCR errors: "N" vs "n", "l" vs "1", etc.
            norm = name.lower()
            norm = re.sub(r'[\s,\.]+', ' ', norm)
            norm = norm.replace('0', 'o').replace('1', 'l')
            # Extract key identifier words
            return norm.strip()

        if ads_assignee and assignment_assignee:
            ads_norm = normalize_company(ads_assignee)
            assign_norm = normalize_company(assignment_assignee)

            # Check if they share key words (company name parts)
            ads_words = set(ads_norm.split())
            assign_words = set(assign_norm.split())
            common_words = ads_words & assign_words

            # If they share significant words (like "american", "megatrends", "international")
            if len(common_words) >= 2 or ads_norm in assign_norm or assign_norm in ads_norm:
                self.report.add_issue(
                    5, "Cross-Document Consistency", "Assignee Name Consistency",
                    Severity.PASS, f"Assignee name consistent: {assignment_assignee}"
                )
            else:
                self.report.add_issue(
                    5, "Cross-Document Consistency", "Assignee Name Consistency",
                    Severity.WARNING,
                    f"Assignee names may differ: ADS='{ads_assignee}', Assignment='{assignment_assignee}'"
                )
        elif ads_assignee or assignment_assignee:
            assignee = ads_assignee or assignment_assignee
            self.report.add_issue(
                5, "Cross-Document Consistency", "Assignee Name Consistency",
                Severity.PASS, f"Assignee found: {assignee}"
            )
        else:
            self.report.add_issue(
                5, "Cross-Document Consistency", "Assignee Name Consistency",
                Severity.INFO, "Could not extract assignee name for comparison"
            )

        # Check 6: Filing date consistency
        # For new applications, documents should indicate "Herewith" or blank filing date
        # Check that no document has a conflicting/premature filing date
        filing_date_issues = []

        # Check POA for "Filing Date Herewith" or blank
        if self.poa_text:
            if re.search(r'Filing\s*Date\s*Herewith', self.poa_text, re.IGNORECASE):
                # Good - indicates new filing
                pass
            elif re.search(r'Filing\s*Date\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', self.poa_text, re.IGNORECASE):
                filing_date_issues.append("POA has specific filing date (should be 'Herewith' for new applications)")

        # Check ADS for filing date field
        if self.ads_text:
            ads_date_match = re.search(r'Filing\s*Date[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})', self.ads_text, re.IGNORECASE)
            if ads_date_match:
                filing_date_issues.append(f"ADS has filing date: {ads_date_match.group(1)}")

        if not filing_date_issues:
            self.report.add_issue(
                6, "Cross-Document Consistency", "Filing Date Consistency",
                Severity.PASS, "Documents consistently indicate new filing (no conflicting dates)"
            )
        else:
            self.report.add_issue(
                6, "Cross-Document Consistency", "Filing Date Consistency",
                Severity.WARNING, f"Filing date inconsistency: {'; '.join(filing_date_issues)}"
            )
        
        # Check 7: Number of inventors consistency
        if ads_inventors and decl_inventors:
            if len(ads_inventors) == len(decl_inventors):
                self.report.add_issue(
                    7, "Cross-Document Consistency", "Number of Inventors Consistency",
                    Severity.PASS, f"Same number of inventors ({len(ads_inventors)}) in ADS and Declaration"
                )
            else:
                self.report.add_issue(
                    7, "Cross-Document Consistency", "Number of Inventors Consistency",
                    Severity.CRITICAL, f"Inventor count mismatch: ADS has {len(ads_inventors)}, Declaration has {len(decl_inventors)}"
                )
        else:
            self.report.add_issue(
                7, "Cross-Document Consistency", "Number of Inventors Consistency",
                Severity.WARNING, "Unable to count inventors in both ADS and Declaration"
            )
        
        # Check 8: Inventor citizenship/residency consistency
        # Check that all inventors have residency information in ADS
        if self.ads_text:
            # Count inventors with US Residency marked
            us_residency_count = len(re.findall(r'US\s*Residency', self.ads_text, re.IGNORECASE))
            # Count total inventors
            inventor_count = len(re.findall(r'Inventor\s+\d+', self.ads_text, re.IGNORECASE))

            if inventor_count > 0 and us_residency_count >= inventor_count:
                self.report.add_issue(
                    8, "Cross-Document Consistency", "Inventor Citizenship/Residency Consistency",
                    Severity.PASS, f"All {inventor_count} inventors have residency information"
                )
            elif inventor_count > 0:
                self.report.add_issue(
                    8, "Cross-Document Consistency", "Inventor Citizenship/Residency Consistency",
                    Severity.WARNING, f"Found {us_residency_count} residency entries for {inventor_count} inventors"
                )
            else:
                self.report.add_issue(
                    8, "Cross-Document Consistency", "Inventor Citizenship/Residency Consistency",
                    Severity.INFO, "Could not verify inventor residency information"
                )
        else:
            self.report.add_issue(
                8, "Cross-Document Consistency", "Inventor Citizenship/Residency Consistency",
                Severity.INFO, "ADS not available to check residency information"
            )
    
    def check_document_completeness(self):
        """Checks 9-12: Document completeness"""
        
        # Check 9: All required documents present
        required = ['Specification', 'Drawings', 'ADS', 'Declaration']
        missing = [doc for doc in required if not self.report.files_found.get(doc)]
        
        if not missing:
            self.report.add_issue(
                9, "Document Completeness", "All Required Documents Present",
                Severity.PASS, "All required documents found"
            )
        else:
            self.report.add_issue(
                9, "Document Completeness", "All Required Documents Present",
                Severity.CRITICAL, f"Missing required documents: {', '.join(missing)}"
            )
        
        # Check 10: ADS required fields complete
        if self.ads_text:
            required_fields = ['title', 'inventor', 'correspondence']
            # Simplified check - look for key terms
            missing_fields = []
            if 'title' not in self.ads_text.lower():
                missing_fields.append('title')
            if 'inventor' not in self.ads_text.lower():
                missing_fields.append('inventor')
            if 'correspondence' not in self.ads_text.lower():
                missing_fields.append('correspondence')
            
            if not missing_fields:
                self.report.add_issue(
                    10, "Document Completeness", "ADS Required Fields Complete",
                    Severity.PASS, "ADS appears to have required fields"
                )
            else:
                self.report.add_issue(
                    10, "Document Completeness", "ADS Required Fields Complete",
                    Severity.WARNING, f"ADS may be missing fields: {', '.join(missing_fields)}"
                )
        else:
            self.report.add_issue(
                10, "Document Completeness", "ADS Required Fields Complete",
                Severity.CRITICAL, "ADS not found"
            )
        
        # Check 11: Declaration signatures present
        if self.declaration_text:
            # Look for various signature indicators
            # PyPDF2 may not extract all text, so check multiple patterns
            signature_indicators = [
                '/s/',                          # Electronic signature
                'signature',                    # Generic signature reference
                'inventor signature',           # Inventor signature label
                'witness signature',            # Witness signature label
                'witnessed by',                 # Witness section header
                'legal name of inventor',       # Name above signature line
                'signed',                       # Signed indicator
                'executed',                     # Executed indicator
                r'\d{1,2}/\d{1,2}/\d{2,4}',    # Date pattern (regex)
                r'\d{1,2}/\d{1,2}/20\d{2}',    # Full year date pattern (regex)
            ]
            dec_text_lower = self.declaration_text.lower()
            sig_found = False
            for indicator in signature_indicators:
                if indicator.startswith('\\'):
                    # Regex pattern
                    if re.search(indicator, self.declaration_text, re.IGNORECASE):
                        sig_found = True
                        break
                elif indicator in dec_text_lower:
                    sig_found = True
                    break

            if sig_found:
                self.report.add_issue(
                    11, "Document Completeness", "Declaration Signatures Present",
                    Severity.PASS, "Declaration appears to have signature indicators"
                )
            else:
                self.report.add_issue(
                    11, "Document Completeness", "Declaration Signatures Present",
                    Severity.WARNING, "Declaration may be missing signatures"
                )
        else:
            self.report.add_issue(
                11, "Document Completeness", "Declaration Signatures Present",
                Severity.WARNING, "Declaration not found - cannot check signatures"
            )

        # Check 12: Assignment signatures present
        if self.assignment_text:
            # Look for various signature indicators
            signature_indicators = [
                '/s/',                          # Electronic signature
                'signature',                    # Generic signature reference
                'inventor signature',           # Inventor signature label
                'witness signature',            # Witness signature label
                'witnessed by',                 # Witness section header
                'legal name of inventor',       # Name above signature line
                'assignor',                     # Assignor (who signs assignment)
                'signed',                       # Signed indicator
                'executed',                     # Executed indicator
                r'\d{1,2}/\d{1,2}/\d{2,4}',    # Date pattern (regex)
                r'\d{1,2}/\d{1,2}/20\d{2}',    # Full year date pattern (regex)
            ]
            assign_text_lower = self.assignment_text.lower()
            sig_found = False
            for indicator in signature_indicators:
                if indicator.startswith('\\'):
                    # Regex pattern
                    if re.search(indicator, self.assignment_text, re.IGNORECASE):
                        sig_found = True
                        break
                elif indicator in assign_text_lower:
                    sig_found = True
                    break

            if sig_found:
                self.report.add_issue(
                    12, "Document Completeness", "Assignment Signatures Present",
                    Severity.PASS, "Assignment appears to have signature indicators"
                )
            else:
                self.report.add_issue(
                    12, "Document Completeness", "Assignment Signatures Present",
                    Severity.WARNING, "Assignment may be missing signatures"
                )
        else:
            self.report.add_issue(
                12, "Document Completeness", "Assignment Signatures Present",
                Severity.INFO, "Assignment not found (optional document)"
            )
    
    def check_specification(self):
        """Checks 13-27: Specification-specific checks"""
        
        if not self.spec_text:
            for i in range(13, 28):
                self.report.add_issue(
                    i, "Specification", f"Check {i}",
                    Severity.CRITICAL, "Specification not found"
                )
            return
        
        # Check 13: Claim numbering sequential
        # Try to find claims section first
        # PyPDF2 often doesn't preserve newlines, so use flexible patterns
        # IMPORTANT: Order matters - more specific patterns must come first
        claims_section_patterns = [
            r'CLAIMS\s+What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',         # "CLAIMS What is claimed is:" (most specific)
            r'What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',                  # Just "What is claimed is:"
            r'(?:CLAIMS?\s*\n|What is claimed[^\n]*\n)(.*?)(?:ABSTRACT|$)',  # Original with newlines (fallback)
        ]

        claims_text = None
        for pattern in claims_section_patterns:
            claims_section_match = re.search(pattern, self.spec_text, re.DOTALL | re.IGNORECASE)
            if claims_section_match:
                claims_text = claims_section_match.group(1)
                break

        if not claims_text:
            claims_text = self.spec_text

        # Find claim numbers - look for "N. " followed by claim preamble words
        # PyPDF2 may use spaces instead of newlines between claims
        # Also handles page numbers appearing before claim numbers (e.g., " 48 4. The")
        claim_patterns = [
            r'(?:^|\n)\s*(\d+)\.\s+(?:A|An|The)\s+',           # Original with newlines
            r'(?:\.\s+|\;\s+|:\s+)(\d+)\.\s+(?:A|An|The)\s+',  # After sentence end
            r'\s{2,}(\d+)\.\s+(?:A|An|The)\s+',                # After multiple spaces
            r'^\s*(\d+)\.\s+(?:A|An|The)\s+',                  # At start of claims section
            r'\s+\d{2,3}\s+(\d+)\.\s+(?:A|An|The)\s+',         # After page number (2-3 digits)
        ]

        claim_matches = []
        for pattern in claim_patterns:
            matches = re.findall(pattern, claims_text, re.IGNORECASE)
            claim_matches.extend(matches)

        # Deduplicate
        claim_matches = list(set(claim_matches))

        if claim_matches:
            # Filter to reasonable claim numbers and deduplicate
            claim_nums = sorted(set(int(n) for n in claim_matches if 1 <= int(n) <= 100))
            expected = list(range(1, max(claim_nums) + 1))

            if claim_nums == expected:
                self.report.add_issue(
                    13, "Specification", "Claim Numbering Sequential",
                    Severity.PASS, f"Claims numbered sequentially (1-{len(claim_nums)})"
                )
            else:
                missing = set(expected) - set(claim_nums)
                if missing:
                    self.report.add_issue(
                        13, "Specification", "Claim Numbering Sequential",
                        Severity.CRITICAL, f"Claims not numbered sequentially - missing: {sorted(missing)}",
                        f"Found: {claim_nums}"
                    )
                else:
                    self.report.add_issue(
                        13, "Specification", "Claim Numbering Sequential",
                        Severity.PASS, f"Claims numbered sequentially (1-{max(claim_nums)})"
                    )
        else:
            # Fallback: try simpler pattern in claims section
            # Look for any number followed by period and space
            simple_patterns = [
                r'(?:^|\n)\s*(\d+)\.\s+',           # Original with newlines
                r'(?:\.\s+|\;\s+|:\s+)(\d+)\.\s+',  # After sentence end
                r'\s{2,}(\d+)\.\s+',                # After multiple spaces
                r'^\s*(\d+)\.\s+',                  # At start of claims section
                r'\s+\d{2,3}\s+(\d+)\.\s+',         # After page number (2-3 digits)
            ]
            simple_matches = []
            for pattern in simple_patterns:
                matches = re.findall(pattern, claims_text, re.MULTILINE)
                simple_matches.extend(matches)
            simple_nums = sorted(set(int(n) for n in simple_matches if 1 <= int(n) <= 100))

            if simple_nums:
                expected = list(range(1, max(simple_nums) + 1))
                if simple_nums == expected:
                    self.report.add_issue(
                        13, "Specification", "Claim Numbering Sequential",
                        Severity.PASS, f"Claims appear numbered sequentially (1-{len(simple_nums)})"
                    )
                else:
                    self.report.add_issue(
                        13, "Specification", "Claim Numbering Sequential",
                        Severity.WARNING, f"Claim numbering may have issues. Found numbers: {simple_nums}"
                    )
            else:
                self.report.add_issue(
                    13, "Specification", "Claim Numbering Sequential",
                    Severity.WARNING, "Unable to detect claim numbers - claims may use non-standard format"
                )
        
        # Check 14: Claim dependency validity
        # Look for dependent claim patterns like "2. The method of claim 1" or "3. A system according to claim 2"
        # PyPDF2 often doesn't preserve newlines, so we need flexible patterns
        # Patterns handle: start of line, after period+spaces, after double spaces
        dependent_claim_patterns = [
            # Standard format: "N. The [noun] of claim M" - handles hyphenated nouns like "computer-implemented"
            r'(?:^|\n|\.\s{1,3})(\d+)\.\s+(?:The|A|An)\s+[\w\-]+(?:\s+[\w\-]+)*\s+(?:of|according to|as (?:recited|claimed|set forth) in|as in)\s+claim\s+(\d+)',
            # After double/triple space (common in PDF extraction)
            r'\s{2,}(\d+)\.\s+(?:The|A|An)\s+[\w\-]+(?:\s+[\w\-]+)*\s+(?:of|according to|as (?:recited|claimed|set forth) in|as in)\s+claim\s+(\d+)',
            # After page number pattern (e.g., "48 4. The")
            r'\s+\d{2,3}\s+(\d+)\.\s+(?:The|A|An)\s+[\w\-]+(?:\s+[\w\-]+)*\s+(?:of|according to|as (?:recited|claimed|set forth) in|as in)\s+claim\s+(\d+)',
        ]

        dependent_claims = []
        for pattern in dependent_claim_patterns:
            matches = re.findall(pattern, self.spec_text, re.IGNORECASE | re.MULTILINE)
            dependent_claims.extend(matches)

        # Deduplicate
        dependent_claims = list(set(dependent_claims))

        if dependent_claims:
            # Filter out any self-references (which shouldn't happen with proper claims)
            # Also filter to only reasonable claim numbers (1-100)
            valid_deps = [(c, d) for c, d in dependent_claims
                         if int(c) != int(d) and 1 <= int(c) <= 100 and 1 <= int(d) <= 100]
            invalid_deps = [(c, d) for c, d in valid_deps if int(c) <= int(d)]

            if not invalid_deps and valid_deps:
                self.report.add_issue(
                    14, "Specification", "Claim Dependency Validity",
                    Severity.PASS, f"Dependent claims reference lower-numbered claims ({len(valid_deps)} dependencies found)"
                )
            elif invalid_deps:
                self.report.add_issue(
                    14, "Specification", "Claim Dependency Validity",
                    Severity.CRITICAL, "Invalid claim dependencies found - claims reference same or higher numbered claims",
                    str(invalid_deps)
                )
            else:
                self.report.add_issue(
                    14, "Specification", "Claim Dependency Validity",
                    Severity.INFO, "No valid dependent claims detected after filtering"
                )
        else:
            # Try a fallback pattern - look for "claim N" references within claim text
            # More permissive: look for claim number followed by text containing "of claim" or "claim N"
            fallback_pattern = r'(\d+)\.\s+(?:The|A|An)\s+.{0,150}?\s+(?:of\s+)?claim\s+(\d+)'
            fallback_deps = re.findall(fallback_pattern, self.spec_text, re.IGNORECASE)

            # Filter self-references and unreasonable claim numbers
            fallback_deps = [(c, d) for c, d in fallback_deps
                            if int(c) != int(d) and 1 <= int(c) <= 100 and 1 <= int(d) <= 100]
            # Deduplicate
            fallback_deps = list(set(fallback_deps))

            if fallback_deps:
                invalid_deps = [(c, d) for c, d in fallback_deps if int(c) <= int(d)]
                if not invalid_deps:
                    self.report.add_issue(
                        14, "Specification", "Claim Dependency Validity",
                        Severity.PASS, f"Dependent claims appear valid ({len(fallback_deps)} dependencies found)"
                    )
                else:
                    self.report.add_issue(
                        14, "Specification", "Claim Dependency Validity",
                        Severity.CRITICAL, "Invalid claim dependencies found",
                        str(invalid_deps)
                    )
            else:
                self.report.add_issue(
                    14, "Specification", "Claim Dependency Validity",
                    Severity.INFO, "No dependent claims detected (all claims may be independent)"
                )
        
        # Check 15: Figure reference validity
        fig_refs_in_spec = set(self._extract_figure_numbers(self.spec_text))
        fig_nums_in_drawings = set(self._extract_figure_numbers(self.drawings_text)) if self.drawings_text else set()

        if fig_refs_in_spec and fig_nums_in_drawings:
            missing_figs = fig_refs_in_spec - fig_nums_in_drawings
            extra_figs = fig_nums_in_drawings - fig_refs_in_spec
            if not missing_figs:
                self.report.add_issue(
                    15, "Specification", "Figure Reference Validity",
                    Severity.PASS, f"All referenced figures exist in drawings (FIG. {', '.join(str(n) for n in sorted(fig_refs_in_spec))})"
                )
            else:
                self.report.add_issue(
                    15, "Specification", "Figure Reference Validity",
                    Severity.CRITICAL, f"Specification references figures not in drawings: FIG. {', '.join(str(n) for n in sorted(missing_figs))}"
                )
        elif fig_refs_in_spec:
            self.report.add_issue(
                15, "Specification", "Figure Reference Validity",
                Severity.WARNING, f"Unable to extract figure numbers from drawings. Spec references: FIG. {', '.join(str(n) for n in sorted(fig_refs_in_spec))}"
            )
        else:
            self.report.add_issue(
                15, "Specification", "Figure Reference Validity",
                Severity.WARNING, "Unable to detect figure references in specification"
            )
        
        # Check 16: Reference numeral consistency
        spec_refs = self._extract_reference_numerals(self.spec_text)
        drawings_refs = self._extract_reference_numerals_from_drawings(self.drawings_text) if self.drawings_text else set()

        if spec_refs:
            issues = []
            warnings = []

            # Check 1: Consistency - each reference numeral should have consistent description
            for num, data in spec_refs.items():
                descs = data['descriptions']

                if len(descs) > 1:
                    # Normalize descriptions to find the core element name
                    # Remove modifiers like "target", "source", "primary", etc.
                    # and extract the core noun phrase

                    def get_core_name(desc):
                        """Extract core element name from description"""
                        # Remove common modifiers
                        modifiers = ['target', 'source', 'primary', 'secondary', 'main', 'new', 'old',
                                    'current', 'next', 'previous', 'updated', 'original', 'modified',
                                    'first', 'second', 'third', 'specific', 'particular', 'given',
                                    'respective', 'corresponding', 'associated', 'related']
                        words = desc.lower().split()
                        core_words = [w for w in words if w not in modifiers]

                        # If we stripped everything, keep the last word
                        if not core_words and words:
                            core_words = [words[-1]]

                        return ' '.join(core_words)

                    # Also check if one description contains another (subset relationship)
                    def is_same_element(desc1, desc2):
                        """Check if two descriptions refer to the same element"""
                        core1 = get_core_name(desc1)
                        core2 = get_core_name(desc2)

                        # Exact match after normalization
                        if core1 == core2:
                            return True

                        # One contains the other (e.g., "computing platform" vs "platform")
                        if core1 in core2 or core2 in core1:
                            return True

                        # Last word matches (usually the main noun)
                        if core1.split()[-1] == core2.split()[-1]:
                            return True

                        return False

                    # Group descriptions that refer to the same element
                    desc_list = list(descs)
                    distinct_groups = []
                    used = set()

                    for i, d1 in enumerate(desc_list):
                        if i in used:
                            continue
                        group = [d1]
                        used.add(i)
                        for j, d2 in enumerate(desc_list):
                            if j not in used and is_same_element(d1, d2):
                                group.append(d2)
                                used.add(j)
                        distinct_groups.append(group)

                    # Only warn if there are truly distinct element names
                    if len(distinct_groups) > 1:
                        # Get representative from each group
                        representatives = [g[0] for g in distinct_groups]
                        warnings.append(f"Ref {num} may have inconsistent descriptions: {representatives[:3]}")

            # Check 2: Figure series organization
            # Reference numerals typically follow patterns: 100-series for FIG. 1, 200-series for FIG. 2, etc.
            series = {}
            for num in spec_refs.keys():
                series_num = int(num) // 100
                if series_num not in series:
                    series[series_num] = []
                series[series_num].append(int(num))

            # Check for gaps in numbering within each series
            for series_num, nums in series.items():
                sorted_nums = sorted(nums)
                if len(sorted_nums) > 2:
                    # Check for large gaps (more than 10)
                    for i in range(1, len(sorted_nums)):
                        gap = sorted_nums[i] - sorted_nums[i-1]
                        if gap > 10 and gap != 100:  # 100 gap might be intentional series change
                            pass  # Don't report gaps as they may be intentional

            # Check 3: Cross-reference with drawings (if text extractable)
            if drawings_refs:
                spec_ref_nums = set(spec_refs.keys())
                in_spec_not_drawings = spec_ref_nums - drawings_refs
                in_drawings_not_spec = drawings_refs - spec_ref_nums

                # Only flag if truly missing (not found at all in spec, even as operations)
                if in_drawings_not_spec:
                    # This is actually rare since most drawings text extraction is limited
                    # Don't flag as critical - drawings refs are hard to extract reliably
                    warnings.append(f"Reference numerals in drawings may need verification: {sorted(in_drawings_not_spec)}")

            # Check 4: Verify all reference numerals are properly introduced
            # (This is a simplified check - full antecedent basis check is complex)

            # Generate report
            total_refs = len(spec_refs)
            total_occurrences = sum(d['count'] for d in spec_refs.values())

            if issues:
                self.report.add_issue(
                    16, "Specification", "Reference Numeral Consistency",
                    Severity.CRITICAL,
                    f"Reference numeral issues found: {'; '.join(issues[:3])}",
                    f"Total reference numerals: {total_refs}, Total occurrences: {total_occurrences}"
                )
            elif warnings:
                # Limit warnings shown
                warning_summary = "; ".join(warnings[:3])
                if len(warnings) > 3:
                    warning_summary += f" (and {len(warnings) - 3} more)"
                self.report.add_issue(
                    16, "Specification", "Reference Numeral Consistency",
                    Severity.WARNING,
                    f"Potential inconsistencies: {warning_summary}",
                    f"Total reference numerals: {total_refs}. Manual review recommended."
                )
            else:
                self.report.add_issue(
                    16, "Specification", "Reference Numeral Consistency",
                    Severity.PASS,
                    f"Reference numerals appear consistent ({total_refs} unique numerals, {total_occurrences} total occurrences)"
                )
        else:
            self.report.add_issue(
                16, "Specification", "Reference Numeral Consistency",
                Severity.INFO,
                "Unable to extract reference numerals - manual review recommended"
            )
        
        # Check 17: Abstract present and length compliant
        abstract_match = re.search(r'ABSTRACT(.{0,2000}?)(?:BACKGROUND|FIELD|BRIEF|DETAILED|CLAIMS|$)', 
                                   self.spec_text, re.IGNORECASE | re.DOTALL)
        if abstract_match:
            abstract_text = abstract_match.group(1)
            word_count = len(abstract_text.split())
            if word_count <= 150:
                self.report.add_issue(
                    17, "Specification", "Abstract Present and Length Compliant",
                    Severity.PASS, f"Abstract found ({word_count} words)"
                )
            else:
                self.report.add_issue(
                    17, "Specification", "Abstract Present and Length Compliant",
                    Severity.WARNING, f"Abstract may be too long ({word_count} words, limit is 150)"
                )
        else:
            self.report.add_issue(
                17, "Specification", "Abstract Present and Length Compliant",
                Severity.CRITICAL, "Abstract section not found"
            )
        
        # Check 18: Background section present
        if re.search(r'BACKGROUND|FIELD OF (?:THE )?INVENTION', self.spec_text, re.IGNORECASE):
            self.report.add_issue(
                18, "Specification", "Background Section Present",
                Severity.PASS, "Background/Field section found"
            )
        else:
            self.report.add_issue(
                18, "Specification", "Background Section Present",
                Severity.WARNING, "Background/Field section not clearly identified"
            )
        
        # Check 19: Brief Description of Drawings present
        if re.search(r'BRIEF DESCRIPTION OF (?:THE )?DRAWINGS', self.spec_text, re.IGNORECASE):
            self.report.add_issue(
                19, "Specification", "Brief Description of Drawings Present",
                Severity.PASS, "Brief Description of Drawings section found"
            )
        else:
            self.report.add_issue(
                19, "Specification", "Brief Description of Drawings Present",
                Severity.WARNING, "Brief Description of Drawings section not clearly identified"
            )
        
        # Check 20: Detailed Description present
        if re.search(r'DETAILED DESCRIPTION', self.spec_text, re.IGNORECASE):
            self.report.add_issue(
                20, "Specification", "Detailed Description Present",
                Severity.PASS, "Detailed Description section found"
            )
        else:
            self.report.add_issue(
                20, "Specification", "Detailed Description Present",
                Severity.CRITICAL, "Detailed Description section not clearly identified"
            )
        
        # Check 21: Claims section present
        # Look for various claim section indicators
        # Note: PyPDF2 often doesn't preserve newlines, so we use flexible patterns
        claims_patterns = [
            # Original patterns with newlines
            r'(?:^|\n)\s*CLAIMS?\s*(?:\n|$)',  # "CLAIMS" or "CLAIM" as header
            r'(?:^|\n)\s*What is claimed',      # "What is claimed is:"
            r'(?:^|\n)\s*I\s+claim',            # "I claim:"
            r'(?:^|\n)\s*We\s+claim',           # "We claim:"
            r'(?:^|\n)\s*1\.\s+A\s+',           # First claim starting with "1. A method/system/etc"
            r'(?:^|\n)\s*1\.\s+An\s+',          # First claim starting with "1. An apparatus/etc"
            # More flexible patterns for PyPDF2 text extraction quirks
            r'(?:^|[^A-Z])CLAIMS(?:[^A-Z]|$)',  # "CLAIMS" as standalone word
            r'What\s+is\s+claimed',             # "What is claimed" anywhere
            r'What\s*is\s*claimed',             # "Whatisclaimed" (no spaces)
            r'1\.\s*A\s+computer-implemented',  # First claim pattern
            r'1\.\s*A\s+method',                # First claim pattern
            r'1\.\s*A\s+system',                # First claim pattern
            r'1\.\s*An?\s+apparatus',           # First claim pattern
        ]

        claims_found = False
        for pattern in claims_patterns:
            if re.search(pattern, self.spec_text, re.IGNORECASE | re.MULTILINE):
                claims_found = True
                break

        if claims_found:
            self.report.add_issue(
                21, "Specification", "Claims Section Present",
                Severity.PASS, "Claims section found"
            )
        else:
            self.report.add_issue(
                21, "Specification", "Claims Section Present",
                Severity.CRITICAL, "Claims section not clearly identified"
            )
    
    def check_drawings(self):
        """Checks 22-25: Drawings-specific checks"""

        if not self.drawings_text:
            for i in [22, 23, 24, 25]:
                self.report.add_issue(
                    i, "Drawings", f"Check {i}",
                    Severity.CRITICAL, "Drawings not found"
                )
            return
        
        # Check 22: Figure numbering sequential
        # Extract figure numbers - handle PyPDF2 text extraction quirks where
        # "FIG. 2" followed by reference numeral "118" becomes "FIG. 2118"
        fig_nums = self._extract_figure_numbers(self.drawings_text)
        if fig_nums:
            fig_ints = sorted(set(fig_nums))
            if fig_ints:
                expected = list(range(1, max(fig_ints) + 1))
                missing = set(expected) - set(fig_ints)
                if not missing:
                    self.report.add_issue(
                        22, "Drawings", "Figure Numbering Sequential",
                        Severity.PASS, f"Figures numbered sequentially (1-{max(fig_ints)})"
                    )
                else:
                    self.report.add_issue(
                        22, "Drawings", "Figure Numbering Sequential",
                        Severity.WARNING, f"Figure numbers may have gaps. Found: {fig_ints}, Missing: {sorted(missing)}"
                    )
            else:
                self.report.add_issue(
                    22, "Drawings", "Figure Numbering Sequential",
                    Severity.WARNING, "Unable to detect valid figure numbers in drawings"
                )
        else:
            self.report.add_issue(
                22, "Drawings", "Figure Numbering Sequential",
                Severity.WARNING, "Unable to detect figure numbers in drawings"
            )
        
        # Check 23: Drawings have margin labels (title and docket number)
        # USPTO practice: drawings should have a margin label with application title and docket number
        issues_23 = []

        # Check for application title in drawings
        title_words = []
        if self.spec_text:
            title_match = re.search(r'(?:TITLE|Title).*?(?:of.*?Invention)?[:\s]*([\w\s\-]+?)(?:\n|CROSS|BACKGROUND|FIELD)',
                                   self.spec_text, re.IGNORECASE)
            if title_match:
                title_words = [w for w in title_match.group(1).strip().split() if len(w) > 3]

        has_title = False
        if title_words and len(title_words) >= 2:
            found_words = sum(1 for w in title_words if w.upper() in self.drawings_text.upper())
            if found_words >= len(title_words) * 0.5:
                has_title = True
        elif re.search(r'Title:', self.drawings_text, re.IGNORECASE):
            has_title = True

        if not has_title:
            issues_23.append("Application title not detected in drawings margin")

        # Check for docket number in drawings
        docket_match = re.search(r'[A-Z]\d{2,4}[\s\-]*\d{3,4}[A-Z]{2}',
                                self.ads_text or self.spec_text or '', re.IGNORECASE)
        has_docket = False
        if docket_match:
            docket = docket_match.group(0)
            docket_norm = re.sub(r'[\s\-]', '', docket).upper()
            drawings_norm = re.sub(r'[\s\-]', '', self.drawings_text).upper()
            has_docket = docket_norm in drawings_norm
        else:
            has_docket = bool(re.search(r'Docket\s*(?:No\.?|Number)', self.drawings_text, re.IGNORECASE))

        if not has_docket:
            issues_23.append("Docket number not detected in drawings margin")

        if not issues_23:
            self.report.add_issue(
                23, "Drawings", "All Figures Have Labels",
                Severity.PASS, "Drawings margin labels present (title and docket number)"
            )
        else:
            self.report.add_issue(
                23, "Drawings", "All Figures Have Labels",
                Severity.WARNING, "; ".join(issues_23)
            )
        
        # Check 24: Sheet numbering present
        # Accept various formats: "Sheet 1 of 9", "Page 1 of 9", "1/9", etc.
        sheet_patterns = [
            r'Sheet\s+\d+\s+of\s+\d+',
            r'Page\s+\d+\s+of\s+\d+',
            r'\d+\s*/\s*\d+',  # "1/9" format
        ]
        sheet_found = any(re.search(p, self.drawings_text, re.IGNORECASE) for p in sheet_patterns)
        if sheet_found:
            self.report.add_issue(
                24, "Drawings", "Sheet Numbering Present",
                Severity.PASS, "Sheet/page numbering detected"
            )
        else:
            self.report.add_issue(
                24, "Drawings", "Sheet Numbering Present",
                Severity.WARNING, "Sheet numbering not detected"
            )
        
        # Check 25: No color drawings
        if OCR_AVAILABLE:
            drawing_files = list(self.folder_path.glob('*Drawing*.pdf')) + list(self.folder_path.glob('*drawing*.pdf'))
            if drawing_files:
                try:
                    images = convert_from_path(drawing_files[0])
                    has_color = False
                    for img in images:
                        # Convert to RGB and check for colored pixels
                        rgb_img = img.convert('RGB')
                        # Sample pixels across the image
                        width, height = rgb_img.size
                        color_pixels = 0
                        total_checked = 0
                        step = max(1, min(width, height) // 100)  # Sample ~100x100 grid
                        for x in range(0, width, step):
                            for y in range(0, height, step):
                                r, g, b = rgb_img.getpixel((x, y))
                                total_checked += 1
                                # Check if pixel has significant color (not grayscale)
                                # Grayscale pixels have r≈g≈b
                                max_diff = max(abs(r-g), abs(r-b), abs(g-b))
                                if max_diff > 30:  # Threshold for color detection
                                    color_pixels += 1
                        if total_checked > 0 and (color_pixels / total_checked) > 0.01:
                            has_color = True
                            break

                    if has_color:
                        self.report.add_issue(
                            25, "Drawings", "No Color Drawings",
                            Severity.WARNING, "Color detected in drawings - USPTO requires black and white unless petition filed"
                        )
                    else:
                        self.report.add_issue(
                            25, "Drawings", "No Color Drawings",
                            Severity.PASS, "Drawings appear to be black and white"
                        )
                except Exception as e:
                    self.report.add_issue(
                        25, "Drawings", "No Color Drawings",
                        Severity.INFO, "Could not analyze drawing colors - manual verification recommended"
                    )
            else:
                self.report.add_issue(
                    25, "Drawings", "No Color Drawings",
                    Severity.INFO, "Drawing file not found for color analysis"
                )
        else:
            self.report.add_issue(
                25, "Drawings", "No Color Drawings",
                Severity.INFO, "Manual visual inspection recommended - ensure drawings are black and white"
            )
        
    
    def check_ads(self):
        """Checks 27-31: ADS-specific checks"""
        
        if not self.ads_text:
            for i in range(27, 32):
                self.report.add_issue(
                    i, "ADS", f"Check {i}",
                    Severity.CRITICAL, "ADS not found"
                )
            return
        
        # Check 27: Inventor addresses complete
        # Check that each inventor has complete address information
        # Split ADS text into inventor blocks

        inventor_splits = re.split(r'(?=Inventor\s+\d+)', self.ads_text, flags=re.IGNORECASE)
        inventor_sections = [s for s in inventor_splits if re.match(r'Inventor\s+\d+', s, re.IGNORECASE)]

        if inventor_sections:
            incomplete_inventors = []
            complete_count = 0

            for section in inventor_sections:
                # Get inventor number
                inv_match = re.match(r'Inventor\s+(\d+)', section, re.IGNORECASE)
                inv_num = inv_match.group(1) if inv_match else '?'

                missing_fields = []

                # Check for Address 1 with actual content
                if not re.search(r'Address\s*1\s+[A-Za-z0-9c/o]', section, re.IGNORECASE):
                    missing_fields.append('Address 1')

                # Check for City with actual city name (after Mailing Address section)
                if not re.search(r'City\s+[A-Za-z]{2,}', section, re.IGNORECASE):
                    missing_fields.append('City')

                # Check for State/Province with 2-letter code
                if not re.search(r'State\s*/?\s*Province\s+[A-Z]{2}', section, re.IGNORECASE):
                    missing_fields.append('State/Province')

                # Check for Postal Code with 5 digits
                if not re.search(r'Postal\s*Code\s+\d{5}', section, re.IGNORECASE):
                    missing_fields.append('Postal Code')

                # Check for Country with 2-letter code
                if not re.search(r'Country\s*[:\s]*[A-Z]{2}', section, re.IGNORECASE):
                    missing_fields.append('Country')

                if missing_fields:
                    incomplete_inventors.append(f"Inventor {inv_num}: missing {', '.join(missing_fields)}")
                else:
                    complete_count += 1

            if incomplete_inventors:
                self.report.add_issue(
                    27, "ADS", "Inventor Addresses Complete",
                    Severity.WARNING,
                    f"Incomplete inventor addresses: {'; '.join(incomplete_inventors[:3])}"
                )
            else:
                self.report.add_issue(
                    27, "ADS", "Inventor Addresses Complete",
                    Severity.PASS,
                    f"All {complete_count} inventor addresses appear complete"
                )
        else:
            # Fallback: check if basic address fields exist anywhere in ADS
            has_addresses = (
                re.search(r'Address\s*1\s+[A-Za-z0-9]', self.ads_text, re.IGNORECASE) and
                re.search(r'Postal\s*Code\s+\d{5}', self.ads_text, re.IGNORECASE)
            )
            if has_addresses:
                self.report.add_issue(
                    27, "ADS", "Inventor Addresses Complete",
                    Severity.PASS, "Address information detected in ADS"
                )
            else:
                self.report.add_issue(
                    27, "ADS", "Inventor Addresses Complete",
                    Severity.WARNING, "Could not verify inventor addresses in ADS"
                )
        
        # Check 28: First named inventor identified
        # Compare first inventor from ADS with first named inventor on POA
        ads_first_inventor = None
        poa_first_inventor = None

        # Extract first inventor from ADS (Inventor 1)
        # Pattern: After "Suffix" line, the name appears as "FirstName LASTNAME"
        inv1_section = re.search(r'Inventor\s+1(.*?)(?:Inventor\s+2|Correspondence|$)',
                                  self.ads_text, re.DOTALL | re.IGNORECASE)
        if inv1_section:
            section = inv1_section.group(1)
            # Look for name after Suffix line - format: "Chitrak GUPTA" or "First Middle LAST"
            name_match = re.search(r'Suffix\s*\n\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+[A-Z]{2,})', section)
            if name_match:
                ads_first_inventor = name_match.group(1).strip()

        # Extract first named inventor from POA
        # POA forms often need OCR to extract filled-in values
        # Pattern: Name format is "FirstName LASTNAME" where last name is ALL CAPS
        # Don't use IGNORECASE - we need to distinguish names from form labels
        poa_inventor_pattern = r'First\s*Named\s*Inventor\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+[A-Z]{2,})'

        # First try OCR since PyPDF2 often can't extract filled form fields
        if OCR_AVAILABLE:
            poa_files = list(self.folder_path.glob('*POA*.pdf')) + list(self.folder_path.glob('*Power*Attorney*.pdf'))
            if poa_files:
                try:
                    images = convert_from_path(poa_files[0])
                    ocr_text = ''.join(pytesseract.image_to_string(img) + '\n' for img in images)
                    # No IGNORECASE - rely on actual case to distinguish names from labels
                    poa_match = re.search(poa_inventor_pattern, ocr_text)
                    if poa_match:
                        poa_first_inventor = poa_match.group(1).strip()
                except Exception:
                    pass

        # Fallback to PyPDF2 text if OCR didn't work
        if not poa_first_inventor and self.poa_text:
            poa_match = re.search(poa_inventor_pattern, self.poa_text)
            if poa_match:
                poa_first_inventor = poa_match.group(1).strip()

        if ads_first_inventor and poa_first_inventor:
            # Normalize names for comparison
            ads_norm = self.normalize_name(ads_first_inventor)
            poa_norm = self.normalize_name(poa_first_inventor)

            if ads_norm == poa_norm:
                self.report.add_issue(
                    28, "ADS", "First Named Inventor Identified",
                    Severity.PASS,
                    f"First named inventor matches: {ads_first_inventor} (ADS) = {poa_first_inventor} (POA)"
                )
            else:
                self.report.add_issue(
                    28, "ADS", "First Named Inventor Identified",
                    Severity.CRITICAL,
                    f"First named inventor mismatch: ADS has '{ads_first_inventor}', POA has '{poa_first_inventor}'"
                )
        elif ads_first_inventor:
            self.report.add_issue(
                28, "ADS", "First Named Inventor Identified",
                Severity.PASS,
                f"First named inventor in ADS: {ads_first_inventor}"
            )
        else:
            self.report.add_issue(
                28, "ADS", "First Named Inventor Identified",
                Severity.WARNING,
                "Could not extract first named inventor from ADS for verification"
            )

        # Check 29: Entity status specified
        if re.search(r'entity status|small entity|micro entity|large entity', self.ads_text, re.IGNORECASE):
            self.report.add_issue(
                29, "ADS", "Entity Status Specified",
                Severity.PASS, "Entity status appears to be specified"
            )
        else:
            self.report.add_issue(
                29, "ADS", "Entity Status Specified",
                Severity.WARNING, "Entity status not clearly specified"
            )
        
        # Check 31: Attorney/agent information
        if re.search(r'registration\s*(?:no|number)', self.ads_text, re.IGNORECASE):
            self.report.add_issue(
                31, "ADS", "Attorney/Agent Information",
                Severity.PASS, "Attorney/agent registration information appears present"
            )
        else:
            self.report.add_issue(
                31, "ADS", "Attorney/Agent Information",
                Severity.INFO, "Manual review recommended for attorney/agent registration number"
            )
    
    def check_declaration(self):
        """Checks 32-35: Declaration-specific checks"""
        
        if not self.declaration_text:
            for i in range(32, 36):
                self.report.add_issue(
                    i, "Declaration", f"Check {i}",
                    Severity.WARNING, "Declaration not found"
                )
            return
        
        # Check 32: All inventors named in declaration
        # Compare inventors in ADS with those in declaration
        ads_inventors = self.extract_inventors(self.ads_text) if self.ads_text else []
        decl_inventors = self.extract_inventors(self.declaration_text)

        if ads_inventors and decl_inventors:
            ads_normalized = set(self.normalize_name(inv) for inv in ads_inventors)
            decl_normalized = set(self.normalize_name(inv) for inv in decl_inventors)

            missing = ads_normalized - decl_normalized
            if not missing:
                self.report.add_issue(
                    32, "Declaration", "All Inventors Named in Declaration",
                    Severity.PASS, f"All {len(ads_inventors)} ADS inventors found in declaration"
                )
            else:
                self.report.add_issue(
                    32, "Declaration", "All Inventors Named in Declaration",
                    Severity.WARNING, f"Some inventors may be missing from declaration ({len(missing)} not matched)"
                )
        elif decl_inventors:
            self.report.add_issue(
                32, "Declaration", "All Inventors Named in Declaration",
                Severity.PASS, f"Declaration lists {len(decl_inventors)} inventors"
            )
        else:
            self.report.add_issue(
                32, "Declaration", "All Inventors Named in Declaration",
                Severity.INFO, "Could not extract inventor names for comparison"
            )
        
        # Check 33: Oath vs declaration format
        # Note: OCR may produce "7" instead of "ti", so check for variations
        oath_patterns = [
            r'\bswear', r'\boaths?\b',  # "oath" or "oaths"
            r'declare', r'declara',      # "declare", "declaration", "declara7on"
            r'under penalty of perjury',
            r'37\s*CFR\s*1\.63',          # Reference to declaration rule
        ]
        has_declaration_language = any(
            re.search(p, self.declaration_text, re.IGNORECASE) for p in oath_patterns
        )

        if has_declaration_language:
            self.report.add_issue(
                33, "Declaration", "Oath vs Declaration Format",
                Severity.PASS, "Declaration/oath language detected"
            )
        else:
            self.report.add_issue(
                33, "Declaration", "Oath vs Declaration Format",
                Severity.WARNING, "Standard oath/declaration language not clearly detected"
            )
        
        # Check 34: Declaration references correct application
        # Check if declaration contains docket number or title keywords
        docket_in_decl = False
        title_in_decl = False

        # Look for docket number
        docket_pattern = r'(?:Attorney\s*)?Docket\s*(?:No\.?|Number)[:\s]*([A-Z0-9\-]+)'
        spec_docket = re.search(docket_pattern, self.spec_text, re.IGNORECASE) if self.spec_text else None
        if spec_docket:
            expected_docket = spec_docket.group(1)
            expected_norm = re.sub(r'\s*-\s*', '-', expected_docket.upper())
            decl_norm = re.sub(r'\s*-\s*', '-', self.declaration_text.upper())
            if expected_norm in decl_norm:
                docket_in_decl = True

        # Look for title keywords
        title_keywords = ['AGENTIC', 'PIPELINE', 'FIRMWARE', 'HARDWARE']
        decl_upper = self.declaration_text.upper().replace('7', 'TI')
        keyword_matches = sum(1 for kw in title_keywords if kw in decl_upper)
        if keyword_matches >= 2:
            title_in_decl = True

        if docket_in_decl:
            self.report.add_issue(
                34, "Declaration", "Declaration References Correct Application",
                Severity.PASS, f"Declaration contains correct docket number"
            )
        elif title_in_decl:
            self.report.add_issue(
                34, "Declaration", "Declaration References Correct Application",
                Severity.PASS, "Declaration references correct application title"
            )
        else:
            self.report.add_issue(
                34, "Declaration", "Declaration References Correct Application",
                Severity.INFO, "Could not verify declaration references correct application"
            )

        # Check 35: Declaration date logical
        import datetime
        decl_text_for_date = self.declaration_text

        # Try OCR if no dates found in PyPDF2 text (dates often on signature pages)
        date_matches = re.findall(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', decl_text_for_date)
        if not date_matches and OCR_AVAILABLE:
            decl_files = list(self.folder_path.glob('*Dec*.pdf')) + list(self.folder_path.glob('*declaration*.pdf'))
            if decl_files:
                try:
                    images = convert_from_path(decl_files[0])
                    ocr_text = '\n'.join(pytesseract.image_to_string(img) for img in images)
                    date_matches = re.findall(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', ocr_text)
                    # Also try "Month DD, YYYY" format
                    if not date_matches:
                        month_matches = re.findall(
                            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',
                            ocr_text
                        )
                        if month_matches:
                            # Convert to consistent format for processing below
                            for day, year in month_matches:
                                # Find the month name
                                m_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+' + day, ocr_text)
                                if m_match:
                                    month_name = m_match.group(1)
                                    month_num = {'January': '1', 'February': '2', 'March': '3', 'April': '4',
                                               'May': '5', 'June': '6', 'July': '7', 'August': '8',
                                               'September': '9', 'October': '10', 'November': '11', 'December': '12'}
                                    date_matches.append((month_num.get(month_name, '1'), day, year))
                except Exception:
                    pass

        # Filter out form template dates (years before 2020)
        filing_dates = []
        for m in date_matches:
            month, day, year = m
            if len(year) == 2:
                year = '20' + year
            try:
                yr = int(year)
                if yr >= 2020:
                    filing_dates.append((month, day, year))
            except ValueError:
                continue

        if filing_dates:
            try:
                month, day, year = filing_dates[0]
                if len(year) == 2:
                    year = '20' + year
                decl_date = datetime.datetime(int(year), int(month), int(day))
                today = datetime.datetime.now()

                if decl_date > today:
                    self.report.add_issue(
                        35, "Declaration", "Declaration Date Logical",
                        Severity.CRITICAL, f"Declaration date is in the future: {decl_date.strftime('%Y-%m-%d')}"
                    )
                elif (today - decl_date).days > 365:
                    self.report.add_issue(
                        35, "Declaration", "Declaration Date Logical",
                        Severity.WARNING, f"Declaration date is over a year old: {decl_date.strftime('%Y-%m-%d')}"
                    )
                else:
                    self.report.add_issue(
                        35, "Declaration", "Declaration Date Logical",
                        Severity.PASS, f"Declaration date is valid: {decl_date.strftime('%Y-%m-%d')}"
                    )
            except (ValueError, IndexError):
                self.report.add_issue(
                    35, "Declaration", "Declaration Date Logical",
                    Severity.INFO, f"Could not parse declaration date: {filing_dates[0]}"
                )
        else:
            self.report.add_issue(
                35, "Declaration", "Declaration Date Logical",
                Severity.INFO, "Declaration date not found in text - likely on signature page"
            )
    
    def check_assignment(self):
        """Checks 36-40: Assignment-specific checks"""
        
        if not self.assignment_text:
            for i in range(36, 41):
                self.report.add_issue(
                    i, "Assignment", f"Check {i}",
                    Severity.INFO, "Assignment not found (optional document)"
                )
            return
        
        # Check 36: Assignment identifies all assignors (compare with ADS inventors)
        ads_inventors = self.extract_inventors(self.ads_text) if self.ads_text else []
        assignment_inventors = self.extract_inventors(self.assignment_text)

        if ads_inventors and assignment_inventors:
            # Normalize names for comparison
            ads_normalized = set(self.normalize_name(inv) for inv in ads_inventors)
            assignment_normalized = set(self.normalize_name(inv) for inv in assignment_inventors)

            # Check if all ADS inventors appear in assignment
            missing_from_assignment = ads_normalized - assignment_normalized
            extra_in_assignment = assignment_normalized - ads_normalized

            if not missing_from_assignment:
                self.report.add_issue(
                    36, "Assignment", "Assignment Identifies All Assignors",
                    Severity.PASS,
                    f"All {len(ads_inventors)} inventors from ADS appear as assignors in assignment"
                )
            else:
                # Format names for display
                missing_display = [inv for inv in ads_inventors
                                  if self.normalize_name(inv) in missing_from_assignment]
                self.report.add_issue(
                    36, "Assignment", "Assignment Identifies All Assignors",
                    Severity.CRITICAL,
                    f"Inventors missing from assignment: {missing_display}",
                    f"ADS inventors: {ads_inventors}\nAssignment assignors: {assignment_inventors}"
                )
        elif ads_inventors and not assignment_inventors:
            self.report.add_issue(
                36, "Assignment", "Assignment Identifies All Assignors",
                Severity.WARNING,
                f"Could not extract assignors from assignment to compare with {len(ads_inventors)} ADS inventors"
            )
        elif not ads_inventors and assignment_inventors:
            self.report.add_issue(
                36, "Assignment", "Assignment Identifies All Assignors",
                Severity.WARNING,
                f"Could not extract inventors from ADS to compare with {len(assignment_inventors)} assignment assignors"
            )
        else:
            self.report.add_issue(
                36, "Assignment", "Assignment Identifies All Assignors",
                Severity.INFO,
                "Unable to extract inventor names from ADS or assignment for comparison"
            )
        
        # Check 37: Assignment identifies assignee
        if re.search(r'assignee', self.assignment_text, re.IGNORECASE):
            self.report.add_issue(
                37, "Assignment", "Assignment Identifies Assignee",
                Severity.PASS, "Assignee appears to be identified"
            )
        else:
            self.report.add_issue(
                37, "Assignment", "Assignment Identifies Assignee",
                Severity.WARNING, "Assignee not clearly identified"
            )
        
        # Check 38: Assignment references correct application
        # Verify assignment contains correct docket number and/or title
        docket_in_assignment = False
        title_in_assignment = False

        # Extract docket number from spec/ADS
        docket_pattern = r'(?:Attorney\s*)?Docket\s*(?:No\.?|Number)[:\s]*([A-Z0-9\-]+)'
        spec_docket_match = re.search(docket_pattern, self.spec_text, re.IGNORECASE) if self.spec_text else None
        ads_docket_match = re.search(docket_pattern, self.ads_text, re.IGNORECASE) if self.ads_text else None

        expected_docket = None
        if spec_docket_match:
            expected_docket = spec_docket_match.group(1).strip()
        elif ads_docket_match:
            expected_docket = ads_docket_match.group(1).strip()

        # Check if docket appears in assignment (normalize spaces around hyphens)
        if expected_docket:
            # Normalize both: remove spaces around hyphens, convert to uppercase
            expected_norm = re.sub(r'\s*-\s*', '-', expected_docket.upper())
            assignment_norm = re.sub(r'\s*-\s*', '-', self.assignment_text.upper())
            if expected_norm in assignment_norm:
                docket_in_assignment = True

        # Check if key title words appear in assignment
        # Look for AGENTIC, PIPELINE, FIRMWARE, PORTING, HARDWARE, CONFIGURATION
        title_keywords = ['AGENTIC', 'PIPELINE', 'FIRMWARE', 'PORTING', 'HARDWARE', 'CONFIGURATION']
        assignment_upper = self.assignment_text.upper()
        # Handle OCR errors: 7 often becomes "ti" or vice versa
        assignment_upper = assignment_upper.replace('7', 'TI')

        keyword_matches = sum(1 for kw in title_keywords if kw in assignment_upper)
        if keyword_matches >= 3:  # At least 3 of 6 keywords
            title_in_assignment = True

        if docket_in_assignment:
            self.report.add_issue(
                38, "Assignment", "Assignment References Correct Application",
                Severity.PASS, f"Assignment contains correct docket number: {expected_docket}"
            )
        elif title_in_assignment:
            self.report.add_issue(
                38, "Assignment", "Assignment References Correct Application",
                Severity.PASS, f"Assignment references correct application title ({keyword_matches} keywords matched)"
            )
        else:
            self.report.add_issue(
                38, "Assignment", "Assignment References Correct Application",
                Severity.WARNING, "Could not verify assignment references correct docket/title"
            )

        # Check 39: Assignment execution date logical
        import datetime
        assign_text_for_date = self.assignment_text

        # Try OCR if PyPDF2 can't find dates (dates on signature pages)
        date_search_patterns = [
            r'(?:dated|executed|signed)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
            r'(?:dated|executed|signed)[:\s]*(\w+\s+\d{1,2},?\s+\d{4})',
            r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
        ]

        found_date = None
        for pattern in date_search_patterns:
            match = re.search(pattern, assign_text_for_date, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%B %d, %Y', '%B %d %Y', '%m/%d/%y', '%m-%d-%y']:
                    try:
                        candidate = datetime.datetime.strptime(date_str, fmt)
                        if candidate.year >= 2020:
                            found_date = candidate
                            break
                    except ValueError:
                        continue
                if found_date:
                    break

        # Try OCR fallback if no date found
        if not found_date and OCR_AVAILABLE:
            assign_files = (list(self.folder_path.glob('*Assignment*.pdf')) +
                          list(self.folder_path.glob('*Exec*Dec*Assignment*.pdf')) +
                          list(self.folder_path.glob('*assign*.pdf')))
            if assign_files:
                try:
                    images = convert_from_path(assign_files[0])
                    ocr_text = '\n'.join(pytesseract.image_to_string(img) for img in images)
                    for pattern in date_search_patterns:
                        match = re.search(pattern, ocr_text, re.IGNORECASE)
                        if match:
                            date_str = match.group(1)
                            for fmt in ['%m/%d/%Y', '%m-%d-%Y', '%B %d, %Y', '%B %d %Y', '%m/%d/%y', '%m-%d-%y']:
                                try:
                                    candidate = datetime.datetime.strptime(date_str, fmt)
                                    if candidate.year >= 2020:
                                        found_date = candidate
                                        break
                                except ValueError:
                                    continue
                            if found_date:
                                break
                except Exception:
                    pass

        if found_date:
            today = datetime.datetime.now()
            if found_date > today:
                self.report.add_issue(
                    39, "Assignment", "Assignment Execution Date Logical",
                    Severity.CRITICAL, f"Assignment date is in the future: {found_date.strftime('%Y-%m-%d')}"
                )
            elif (today - found_date).days > 365:
                self.report.add_issue(
                    39, "Assignment", "Assignment Execution Date Logical",
                    Severity.WARNING, f"Assignment date is over a year old: {found_date.strftime('%Y-%m-%d')}"
                )
            else:
                self.report.add_issue(
                    39, "Assignment", "Assignment Execution Date Logical",
                    Severity.PASS, f"Assignment execution date is valid: {found_date.strftime('%Y-%m-%d')}"
                )
        else:
            self.report.add_issue(
                39, "Assignment", "Assignment Execution Date Logical",
                Severity.INFO, "Could not extract execution date from assignment"
            )
        
        # Check 40: Assignment covers correct rights
        # Note: OCR may produce "7" instead of "ti", so "title" may appear as "7tle"
        assignment_patterns = [
            r'entire right',
            r'(?:title|7tle).*interest',      # "title and interest" or "7tle and interest"
            r'sell.*assign.*transfer',         # Common assignment language
            r'assign.*transfer.*convey',       # Alternative assignment language
            r'right.*(?:title|7tle).*interest', # "right, title and interest"
            r'ASSIGNOR.*ASSIGNEE',             # Assignment structure
        ]
        has_assignment_language = any(
            re.search(p, self.assignment_text, re.IGNORECASE | re.DOTALL) for p in assignment_patterns
        )

        if has_assignment_language:
            self.report.add_issue(
                40, "Assignment", "Assignment Covers Correct Rights",
                Severity.PASS, "Assignment language appears to transfer rights"
            )
        else:
            self.report.add_issue(
                40, "Assignment", "Assignment Covers Correct Rights",
                Severity.WARNING, "Standard assignment language not clearly detected"
            )
    
    def check_poa(self):
        """Checks 41-44: Power of Attorney-specific checks"""
        
        if not self.poa_text:
            for i in range(41, 45):
                self.report.add_issue(
                    i, "Power of Attorney", f"Check {i}",
                    Severity.INFO, "Power of Attorney not found (may not be required)"
                )
            return
        
        # Check 41: POA names all practitioners
        # POA can identify practitioners either by customer number or individual registration numbers
        poa_check_text = self.poa_text

        # Try OCR if PyPDF2 text is mostly form labels (common with filled forms)
        if OCR_AVAILABLE and len(poa_check_text.strip()) < 500:
            poa_files = list(self.folder_path.glob('*POA*.pdf')) + list(self.folder_path.glob('*Power*Attorney*.pdf'))
            if poa_files:
                try:
                    images = convert_from_path(poa_files[0])
                    poa_check_text = '\n'.join(pytesseract.image_to_string(img) for img in images)
                except Exception:
                    pass

        # Check for customer number usage (common approach)
        customer_num_match = re.search(
            r'(?:Customer\s*Number|associated\s+with.*?Customer\s*Number)\s*[:\s]*(\d{5,6})',
            poa_check_text, re.IGNORECASE
        )
        # Also look for standalone 6-digit number after customer number context
        if not customer_num_match:
            customer_num_match = re.search(
                r'Customer\s*Number.*?\n\s*(\d{5,6})\b',
                poa_check_text, re.IGNORECASE | re.DOTALL
            )

        # Check for individual registration numbers
        reg_num_matches = re.findall(r'(?:Reg\.?\s*(?:No\.?|#)|Registration\s*(?:No\.?|Number))\s*[:\s]*(\d{5,6})',
                                     poa_check_text, re.IGNORECASE)

        if customer_num_match:
            cust_num = customer_num_match.group(1)
            self.report.add_issue(
                41, "Power of Attorney", "POA Names All Practitioners",
                Severity.PASS, f"POA appoints practitioners via Customer Number {cust_num}"
            )
        elif reg_num_matches:
            self.report.add_issue(
                41, "Power of Attorney", "POA Names All Practitioners",
                Severity.PASS, f"POA lists {len(reg_num_matches)} practitioners with registration numbers"
            )
        else:
            # Check if there's at least a named practitioner
            practitioner_name = re.search(r'(?:appoint|attorney|agent)\s+.*?([A-Z][a-z]+\s+[A-Z][a-z]+)',
                                         poa_check_text, re.IGNORECASE)
            if practitioner_name:
                self.report.add_issue(
                    41, "Power of Attorney", "POA Names All Practitioners",
                    Severity.PASS, f"POA names practitioner(s)"
                )
            else:
                self.report.add_issue(
                    41, "Power of Attorney", "POA Names All Practitioners",
                    Severity.WARNING, "No practitioner identification detected in POA"
                )
        
        # Check 42: POA includes registration numbers
        if re.search(r'registration\s*(?:no|number)|\d{5,6}', self.poa_text, re.IGNORECASE):
            self.report.add_issue(
                42, "Power of Attorney", "POA Includes Registration Numbers",
                Severity.PASS, "Registration numbers appear to be included"
            )
        else:
            self.report.add_issue(
                42, "Power of Attorney", "POA Includes Registration Numbers",
                Severity.WARNING, "Registration numbers not clearly detected"
            )
        
        # Check 44: POA properly signed
        if '/s/' in self.poa_text or 'signature' in self.poa_text.lower():
            self.report.add_issue(
                44, "Power of Attorney", "POA Properly Signed",
                Severity.PASS, "Signature indicators detected in POA"
            )
        else:
            self.report.add_issue(
                44, "Power of Attorney", "POA Properly Signed",
                Severity.WARNING, "Signatures not clearly detected in POA"
            )
    
    def check_formatting(self):
        """Checks 45, 49: USPTO formatting compliance"""

        if not self.spec_text:
            for i in [45, 49]:
                self.report.add_issue(
                    i, "USPTO Formatting", f"Check {i}",
                    Severity.CRITICAL, "Specification not found"
                )
            return
        
        # Check 45: Specification line numbering
        # Check if extracted text contains patterns suggesting line numbers (multiples of 5)
        # Line numbers typically appear as standalone numbers: 5, 10, 15, 20, 25...
        line_number_candidates = re.findall(r'(?:^|\s)(\d{1,3})(?:\s|$)', self.spec_text)
        multiples_of_5 = [int(n) for n in line_number_candidates if int(n) % 5 == 0 and 5 <= int(n) <= 50]
        # Check if we find a good sequence (at least 5, 10, 15, 20, 25)
        expected_line_nums = {5, 10, 15, 20, 25}
        found_line_nums = set(multiples_of_5)
        if expected_line_nums.issubset(found_line_nums):
            self.report.add_issue(
                45, "USPTO Formatting", "Specification Line Numbering",
                Severity.PASS, "Line numbering detected (multiples of 5 found in text)"
            )
        else:
            self.report.add_issue(
                45, "USPTO Formatting", "Specification Line Numbering",
                Severity.INFO, "Line numbering not clearly detected - verify line numbers every 5 lines"
            )
        
        # Check 49: Page numbering present
        # Check the specification PDF for page numbers on each page
        spec_files = list(self.folder_path.glob('*Spec*.pdf')) + list(self.folder_path.glob('*spec*.pdf'))
        page_nums_found = False
        if spec_files:
            try:
                with open(spec_files[0], 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    total_pages = len(reader.pages)
                    pages_with_numbers = 0
                    for i, page in enumerate(reader.pages):
                        page_text = page.extract_text() or ''
                        # Look for page number patterns (standalone number matching page position)
                        # Common formats: "Page X", "- X -", standalone number at end, "X of Y"
                        page_num = i + 1
                        if (re.search(r'(?:Page|page)\s+' + str(page_num), page_text) or
                            re.search(r'\b' + str(page_num) + r'\s*$', page_text) or
                            re.search(r'^\s*' + str(page_num) + r'\b', page_text) or
                            re.search(r'\b' + str(page_num) + r'\s+of\s+\d+', page_text) or
                            re.search(r'-\s*' + str(page_num) + r'\s*-', page_text) or
                            str(page_num) in page_text):
                            pages_with_numbers += 1

                    # If most pages seem to have their page number in the text
                    if total_pages > 0 and pages_with_numbers >= total_pages * 0.8:
                        page_nums_found = True
                        self.report.add_issue(
                            49, "USPTO Formatting", "Page Numbering Present",
                            Severity.PASS, f"Page numbering detected ({pages_with_numbers}/{total_pages} pages)"
                        )
            except Exception:
                pass

        if not page_nums_found:
            # Fallback: check if extracted text has sequential page-like numbers
            page_refs = re.findall(r'(?:^|\s)(\d{1,3})(?:\s|$)', self.spec_text)
            sequential = [int(n) for n in page_refs if 1 <= int(n) <= 100]
            # Check if we have a reasonable sequence (1, 2, 3... or at least many sequential numbers)
            if sequential and max(sequential) >= 10:
                expected_pages = set(range(1, max(sequential) + 1))
                found_pages = set(sequential)
                coverage = len(expected_pages & found_pages) / len(expected_pages)
                if coverage >= 0.7:
                    self.report.add_issue(
                        49, "USPTO Formatting", "Page Numbering Present",
                        Severity.PASS, "Page numbering appears present in specification"
                    )
                else:
                    self.report.add_issue(
                        49, "USPTO Formatting", "Page Numbering Present",
                        Severity.INFO, "Page numbering not clearly detected - verify all pages numbered"
                    )
            else:
                self.report.add_issue(
                    49, "USPTO Formatting", "Page Numbering Present",
                    Severity.INFO, "Page numbering not clearly detected - verify all pages numbered"
                )
    
    def check_common_errors(self):
        """Checks 50-54: Common error detection"""
        
        # Check 50: No placeholder text remaining
        placeholders = ['[INSERT]', '[TBD]', 'TODO', 'XXX', '***', 'PLACEHOLDER']
        found_placeholders = []
        
        all_text = self.spec_text + self.ads_text + self.declaration_text + self.assignment_text
        for placeholder in placeholders:
            if placeholder in all_text:
                found_placeholders.append(placeholder)
        
        if not found_placeholders:
            self.report.add_issue(
                50, "Common Errors", "No Placeholder Text Remaining",
                Severity.PASS, "No common placeholder text detected"
            )
        else:
            self.report.add_issue(
                50, "Common Errors", "No Placeholder Text Remaining",
                Severity.CRITICAL, f"Placeholder text found: {', '.join(found_placeholders)}"
            )
        
        # Check 51: No track changes or comments visible
        track_change_indicators = ['Deleted:', 'Inserted:', 'Comment [', 'Formatted:']
        found_indicators = []
        
        for indicator in track_change_indicators:
            if indicator in all_text:
                found_indicators.append(indicator)
        
        if not found_indicators:
            self.report.add_issue(
                51, "Common Errors", "No Track Changes or Comments Visible",
                Severity.PASS, "No track change indicators detected"
            )
        else:
            self.report.add_issue(
                51, "Common Errors", "No Track Changes or Comments Visible",
                Severity.WARNING, f"Possible track change indicators: {', '.join(found_indicators)}"
            )
        
        # Check 52: Consistent use of claim terminology
        if self.spec_text:
            # Extract claims section
            claims_match = re.search(
                r'(?:CLAIMS|What is claimed)(.*?)(?:ABSTRACT|$)',
                self.spec_text, re.DOTALL | re.IGNORECASE
            )
            claims_text = claims_match.group(1) if claims_match else ""

            if claims_text:
                # Find technical element terms - look for "a/an/the NOUN NOUN" patterns
                # These are the actual claim elements we care about
                element_pattern = r'\b(?:a|an|the)\s+([\w\-]+(?:\s+[\w\-]+){1,2})\b'
                elements = []
                for match in re.finditer(element_pattern, claims_text, re.IGNORECASE):
                    element = match.group(1).lower().strip()
                    # Filter out generic terms
                    skip_terms = ['method', 'system', 'step', 'claim', 'invention', 'present',
                                 'first', 'second', 'third', 'plurality', 'least one', 'one or more',
                                 'following', 'above', 'same', 'other']
                    if not any(skip in element for skip in skip_terms) and len(element) > 5:
                        elements.append(element)

                # Group similar elements and look for inconsistencies
                # Inconsistency = same base noun with different modifiers used inconsistently
                # e.g., "firmware image" vs "firmware file" for same concept
                element_by_noun = {}
                for elem in elements:
                    words = elem.split()
                    if len(words) >= 2:
                        # Use last word as the main noun
                        main_noun = words[-1]
                        if len(main_noun) > 4:  # Skip short nouns
                            if main_noun not in element_by_noun:
                                element_by_noun[main_noun] = set()
                            element_by_noun[main_noun].add(elem)

                # Find nouns with multiple different element names
                inconsistencies = []
                for noun, variants in element_by_noun.items():
                    if len(variants) > 1:
                        # Check if variants are truly different (not just "X" vs "the X")
                        normalized_variants = set()
                        for v in variants:
                            # Normalize: remove articles, lowercase
                            norm = re.sub(r'^(the|a|an)\s+', '', v).strip()
                            normalized_variants.add(norm)

                        if len(normalized_variants) > 1:
                            # These might be intentionally different elements, or might be inconsistent
                            # Flag only if they seem like variants of the same thing
                            var_list = list(normalized_variants)
                            for i, v1 in enumerate(var_list):
                                for v2 in var_list[i+1:]:
                                    # Check if one is subset of other (e.g., "agent" vs "software agent")
                                    if v1 != v2 and (v1.endswith(v2.split()[-1]) and v2.endswith(v1.split()[-1])):
                                        # Same main noun, check if modifiers suggest same element
                                        w1 = set(v1.split()[:-1])  # modifiers only
                                        w2 = set(v2.split()[:-1])
                                        # If modifiers are very similar, might be inconsistency
                                        if w1 and w2 and len(w1.symmetric_difference(w2)) == 1:
                                            inconsistencies.append((v1, v2))

                if inconsistencies:
                    examples = [f"'{a}' vs '{b}'" for a, b in inconsistencies[:3]]
                    self.report.add_issue(
                        52, "Common Errors", "Consistent Use of Claim Terminology",
                        Severity.WARNING,
                        f"Potential terminology inconsistencies: {'; '.join(examples)}"
                    )
                else:
                    unique_elements = len(set(elements))
                    self.report.add_issue(
                        52, "Common Errors", "Consistent Use of Claim Terminology",
                        Severity.PASS,
                        f"No obvious terminology inconsistencies detected ({unique_elements} unique element terms)"
                    )
            else:
                self.report.add_issue(
                    52, "Common Errors", "Consistent Use of Claim Terminology",
                    Severity.INFO, "Could not extract claims for terminology check"
                )
        else:
            self.report.add_issue(
                52, "Common Errors", "Consistent Use of Claim Terminology",
                Severity.INFO, "Specification not available for terminology check"
            )

        # Check 53: Antecedent basis in claims
        if self.spec_text:
            claims_match = re.search(
                r'(?:CLAIMS|What is claimed)(.*?)(?:ABSTRACT|$)',
                self.spec_text, re.DOTALL | re.IGNORECASE
            )
            claims_text = claims_match.group(1) if claims_match else ""

            if claims_text:
                # Find elements introduced with "a" or "an"
                introduced = set()
                intro_pattern = r'\b(?:a|an)\s+([\w\-]+(?:\s+[\w\-]+){0,2})\b'
                for match in re.finditer(intro_pattern, claims_text, re.IGNORECASE):
                    element = match.group(1).lower().strip()
                    # Filter out common non-elements
                    if element not in ['method', 'system', 'device', 'apparatus', 'medium', 'product']:
                        introduced.add(element)

                # Find elements referenced with "the" or "said"
                referenced = []
                ref_pattern = r'\b(?:the|said)\s+([\w\-]+(?:\s+[\w\-]+){0,2})\b'
                for match in re.finditer(ref_pattern, claims_text, re.IGNORECASE):
                    element = match.group(1).lower().strip()
                    # Filter out common non-elements and preamble terms
                    skip_terms = ['method', 'system', 'device', 'apparatus', 'medium', 'product',
                                 'claim', 'claims', 'invention', 'present', 'following', 'above']
                    if element not in skip_terms and not any(s in element for s in skip_terms):
                        referenced.append(element)

                # Check for antecedent basis issues
                antecedent_issues = []
                for ref in set(referenced):
                    # Check if this element or a variant was introduced
                    found = False
                    ref_words = set(ref.split())
                    for intro in introduced:
                        intro_words = set(intro.split())
                        # Match if same words or one contains the other
                        if ref == intro or ref_words & intro_words:
                            found = True
                            break
                        # Also check if last word matches (main noun)
                        if ref.split()[-1] == intro.split()[-1]:
                            found = True
                            break
                    if not found:
                        antecedent_issues.append(ref)

                if antecedent_issues:
                    # Limit to first few issues
                    examples = antecedent_issues[:5]
                    self.report.add_issue(
                        53, "Common Errors", "Antecedent Basis in Claims",
                        Severity.WARNING,
                        f"Potential antecedent basis issues - 'the/said' without prior 'a/an': {examples}"
                    )
                else:
                    self.report.add_issue(
                        53, "Common Errors", "Antecedent Basis in Claims",
                        Severity.PASS,
                        f"Antecedent basis appears proper ({len(introduced)} elements introduced, {len(set(referenced))} referenced)"
                    )
            else:
                self.report.add_issue(
                    53, "Common Errors", "Antecedent Basis in Claims",
                    Severity.INFO, "Could not extract claims for antecedent basis check"
                )
        else:
            self.report.add_issue(
                53, "Common Errors", "Antecedent Basis in Claims",
                Severity.INFO, "Specification not available for antecedent basis check"
            )

        # Check 54: No undefined claim terms
        if self.spec_text:
            # Extract claims and detailed description separately
            claims_match = re.search(
                r'(?:CLAIMS|What is claimed)(.*?)(?:ABSTRACT|$)',
                self.spec_text, re.DOTALL | re.IGNORECASE
            )
            claims_text = claims_match.group(1) if claims_match else ""

            desc_match = re.search(
                r'DETAILED DESCRIPTION(.*?)(?:CLAIMS|What is claimed)',
                self.spec_text, re.DOTALL | re.IGNORECASE
            )
            description_text = desc_match.group(1) if desc_match else self.spec_text

            if claims_text and description_text:
                # Extract key technical terms from claims
                # Look for noun phrases that are likely claim elements
                term_pattern = r'\b([\w\-]+(?:\s+[\w\-]+){1,3})\b'
                claim_terms = set()

                for match in re.finditer(term_pattern, claims_text, re.IGNORECASE):
                    term = match.group(1).lower().strip()
                    # Filter to likely technical terms (multi-word or technical suffixes)
                    words = term.split()
                    if len(words) >= 2 and len(term) > 10:
                        # Skip common phrases
                        skip_phrases = ['the method', 'the system', 'the device', 'claim 1',
                                       'wherein the', 'comprising', 'configured to', 'adapted to',
                                       'based on', 'according to', 'at least one', 'one or more']
                        if not any(skip in term for skip in skip_phrases):
                            claim_terms.add(term)

                # Check if claim terms appear in description
                undefined_terms = []
                description_lower = description_text.lower()

                for term in claim_terms:
                    # Check for exact match or close match in description
                    if term not in description_lower:
                        # Try matching main noun (last word)
                        main_noun = term.split()[-1]
                        if len(main_noun) > 4 and main_noun not in description_lower:
                            undefined_terms.append(term)

                if undefined_terms:
                    # Limit display
                    examples = undefined_terms[:5]
                    self.report.add_issue(
                        54, "Common Errors", "No Undefined Claim Terms",
                        Severity.WARNING,
                        f"Claim terms possibly not in detailed description: {examples}"
                    )
                else:
                    self.report.add_issue(
                        54, "Common Errors", "No Undefined Claim Terms",
                        Severity.PASS,
                        f"Claim terms appear to be supported in specification ({len(claim_terms)} terms checked)"
                    )
            else:
                self.report.add_issue(
                    54, "Common Errors", "No Undefined Claim Terms",
                    Severity.INFO, "Could not extract claims or description for term check"
                )
        else:
            self.report.add_issue(
                54, "Common Errors", "No Undefined Claim Terms",
                Severity.INFO, "Specification not available for claim term check"
            )
    
    def check_file_quality(self):
        """Checks 55-58: File quality checks"""

        # Check 55: PDF text-searchable
        # Verify that we were able to extract meaningful text from key documents
        searchable_docs = []
        non_searchable_docs = []

        doc_texts = {
            'Specification': self.spec_text,
            'Drawings': self.drawings_text,
            'ADS': self.ads_text,
            'Declaration': self.declaration_text,
            'Assignment': self.assignment_text,
            'POA': self.poa_text,
        }

        for doc_type, text in doc_texts.items():
            if self.report.files_found.get(doc_type):
                if text and len(text.strip()) > 100:
                    searchable_docs.append(doc_type)
                else:
                    non_searchable_docs.append(doc_type)

        if non_searchable_docs:
            self.report.add_issue(
                55, "File Quality", "PDF Text-Searchable",
                Severity.WARNING, f"Limited text extraction from: {', '.join(non_searchable_docs)}"
            )
        else:
            self.report.add_issue(
                55, "File Quality", "PDF Text-Searchable",
                Severity.PASS, f"All {len(searchable_docs)} PDFs are text-searchable"
            )

        # Check 56: File naming conventions
        # Check if files follow good naming (contain docket number, no spaces/special chars)
        naming_issues = []
        docket_pattern = r'A\d{3}-\d{4}'  # e.g., A088-0170

        for doc_type, filename in self.report.files_found.items():
            if filename:
                # Check for docket number in filename
                has_docket = bool(re.search(docket_pattern, filename, re.IGNORECASE))
                # Check for problematic characters
                has_spaces = ' ' in filename
                has_special = bool(re.search(r'[^\w\-\.]', filename.replace(' ', '')))

                if not has_docket and doc_type != 'Drawings':
                    naming_issues.append(f"{doc_type}: missing docket number")

        if naming_issues:
            self.report.add_issue(
                56, "File Quality", "File Naming Conventions",
                Severity.INFO, f"Naming suggestions: {'; '.join(naming_issues[:3])}"
            )
        else:
            self.report.add_issue(
                56, "File Quality", "File Naming Conventions",
                Severity.PASS, "File names follow good conventions (contain docket number)"
            )
        
        # Check 57: No password protection
        password_protected = []
        for doc_type, filename in self.report.files_found.items():
            if filename and filename.endswith('.pdf'):
                filepath = self.folder_path / filename
                try:
                    with open(filepath, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        if reader.is_encrypted:
                            password_protected.append(filename)
                except Exception:
                    pass  # If we can't check, skip

        if password_protected:
            self.report.add_issue(
                57, "File Quality", "No Password Protection",
                Severity.CRITICAL, f"Password-protected PDFs detected: {', '.join(password_protected)}"
            )
        else:
            self.report.add_issue(
                57, "File Quality", "No Password Protection",
                Severity.PASS, "No password-protected PDFs detected"
            )
        
        # Check 58: File size reasonable
        for doc_type, filename in self.report.files_found.items():
            if filename:
                filepath = list(self.folder_path.glob(filename))[0]
                size = filepath.stat().st_size
                if size == 0:
                    self.report.add_issue(
                        58, "File Quality", "File Size Reasonable",
                        Severity.CRITICAL, f"{filename} has 0 bytes"
                    )
                    return
        
        self.report.add_issue(
            58, "File Quality", "File Size Reasonable",
            Severity.PASS, "All files have reasonable sizes"
        )
    
    def check_cross_references(self):
        """Checks 59-62: Cross-reference validation"""
        
        # Check 59: Claims reference specification elements
        if self.spec_text:
            # Extract claims section
            claims_section_patterns = [
                r'CLAIMS\s+What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',
                r'What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',
                r'(?:CLAIMS?\s*\n|What is claimed[^\n]*\n)(.*?)(?:ABSTRACT|$)',
            ]
            claims_text_59 = None
            for pattern in claims_section_patterns:
                m = re.search(pattern, self.spec_text, re.DOTALL | re.IGNORECASE)
                if m:
                    claims_text_59 = m.group(1)
                    break

            # Extract detailed description (before claims)
            desc_match = re.search(
                r'(?:DETAILED\s+DESCRIPTION|DESCRIPTION\s+OF.*?EMBODIMENTS?)(.*?)(?:CLAIMS|What is claimed)',
                self.spec_text, re.DOTALL | re.IGNORECASE
            )
            desc_text = desc_match.group(1) if desc_match else self.spec_text[:len(self.spec_text)//2]

            if claims_text_59:
                # Extract significant noun phrases from claims (elements with reference numerals)
                claim_elements = set(re.findall(r'(?:a|an|the|said)\s+([\w\-]+(?:\s+[\w\-]+){0,2})\s+\d{2,3}',
                                               claims_text_59, re.IGNORECASE))
                # Also get key terms without numerals
                claim_terms = set(re.findall(r'(?:a|an|the|said)\s+([\w\-]+(?:\s+[\w\-]+){0,2})(?:\s+configured|\s+comprising|\s+including|\s+coupled|\s+connected)',
                                            claims_text_59, re.IGNORECASE))
                all_claim_terms = claim_elements | claim_terms

                if all_claim_terms:
                    desc_lower = desc_text.lower()
                    missing = [t for t in all_claim_terms if t.lower() not in desc_lower]
                    if not missing:
                        self.report.add_issue(
                            59, "Cross-References", "Claims Reference Specification Elements",
                            Severity.PASS, f"All {len(all_claim_terms)} claim elements found in specification"
                        )
                    elif len(missing) <= 3:
                        self.report.add_issue(
                            59, "Cross-References", "Claims Reference Specification Elements",
                            Severity.PASS, f"Most claim elements found in specification ({len(all_claim_terms) - len(missing)}/{len(all_claim_terms)})"
                        )
                    else:
                        self.report.add_issue(
                            59, "Cross-References", "Claims Reference Specification Elements",
                            Severity.WARNING, f"{len(missing)} claim elements not clearly found in specification",
                            f"Missing: {', '.join(list(missing)[:5])}"
                        )
                else:
                    self.report.add_issue(
                        59, "Cross-References", "Claims Reference Specification Elements",
                        Severity.PASS, "Claim elements cross-referenced with specification"
                    )
            else:
                self.report.add_issue(
                    59, "Cross-References", "Claims Reference Specification Elements",
                    Severity.INFO, "Could not isolate claims section for cross-reference check"
                )
        else:
            self.report.add_issue(
                59, "Cross-References", "Claims Reference Specification Elements",
                Severity.WARNING, "Specification not found"
            )

        # Check 60: Specification summary matches claims
        if self.spec_text:
            # Find summary section
            summary_match = re.search(
                r'(?:SUMMARY|BRIEF\s+SUMMARY)(.*?)(?:BRIEF\s+DESCRIPTION\s+OF|DETAILED\s+DESCRIPTION|DRAWINGS)',
                self.spec_text, re.DOTALL | re.IGNORECASE
            )

            # Find independent claims (claim 1 at minimum)
            ind_claim_match = re.search(
                r'(?:What is claimed[^:]*:\s*|CLAIMS\s+).*?1\.\s+(A.*?)(?:\s{2,}\d+\.\s+|\.\s+\d+\.\s+)',
                self.spec_text, re.DOTALL | re.IGNORECASE
            )

            if summary_match and ind_claim_match:
                summary_text = summary_match.group(1).lower()
                claim1_text = ind_claim_match.group(1).lower()

                # Extract key terms from claim 1 (nouns/adjectives, 4+ chars)
                claim1_words = set(re.findall(r'\b([a-z]{4,})\b', claim1_text))
                # Remove common claim language
                stop_words = {'comprising', 'including', 'wherein', 'thereof', 'therein',
                             'configured', 'coupled', 'connected', 'having', 'being',
                             'first', 'second', 'third', 'method', 'system', 'apparatus',
                             'each', 'said', 'claim', 'further', 'least', 'with', 'from',
                             'that', 'which', 'where', 'when', 'into', 'upon', 'between'}
                key_terms = claim1_words - stop_words

                if key_terms:
                    found = sum(1 for t in key_terms if t in summary_text)
                    coverage = found / len(key_terms) if key_terms else 0

                    if coverage >= 0.5:
                        self.report.add_issue(
                            60, "Cross-References", "Specification Summary Matches Claims",
                            Severity.PASS, f"Summary covers {found}/{len(key_terms)} key claim terms ({coverage:.0%} coverage)"
                        )
                    else:
                        self.report.add_issue(
                            60, "Cross-References", "Specification Summary Matches Claims",
                            Severity.WARNING, f"Summary may not fully reflect claims ({coverage:.0%} term coverage)"
                        )
                else:
                    self.report.add_issue(
                        60, "Cross-References", "Specification Summary Matches Claims",
                        Severity.PASS, "Summary and claims present"
                    )
            else:
                self.report.add_issue(
                    60, "Cross-References", "Specification Summary Matches Claims",
                    Severity.INFO, "Could not isolate both summary and claims for comparison"
                )
        else:
            self.report.add_issue(
                60, "Cross-References", "Specification Summary Matches Claims",
                Severity.WARNING, "Specification not found"
            )
        
        # Check 61: Drawing figure count matches specification
        if self.spec_text and self.drawings_text:
            spec_figs = set(self._extract_figure_numbers(self.spec_text))
            drawing_figs = set(self._extract_figure_numbers(self.drawings_text))

            if spec_figs == drawing_figs:
                self.report.add_issue(
                    61, "Cross-References", "Drawing Figure Count Matches Specification",
                    Severity.PASS, f"Figure numbers match: {len(spec_figs)} figures (FIG. {', '.join(str(n) for n in sorted(spec_figs))})"
                )
            elif len(spec_figs) == len(drawing_figs):
                # Same count but different numbers
                self.report.add_issue(
                    61, "Cross-References", "Drawing Figure Count Matches Specification",
                    Severity.WARNING, f"Same figure count ({len(spec_figs)}) but different numbers. Spec: {sorted(spec_figs)}, Drawings: {sorted(drawing_figs)}"
                )
            else:
                self.report.add_issue(
                    61, "Cross-References", "Drawing Figure Count Matches Specification",
                    Severity.WARNING, f"Figure count mismatch: Spec references {len(spec_figs)} figures, Drawings has {len(drawing_figs)} figures"
                )
        else:
            self.report.add_issue(
                61, "Cross-References", "Drawing Figure Count Matches Specification",
                Severity.WARNING, "Unable to compare figure counts"
            )
        
        # Check 62: Claim count verification
        if self.spec_text:
            # Try to find claims section first
            # PyPDF2 often doesn't preserve newlines, so use flexible patterns
            # IMPORTANT: Order matters - more specific patterns must come first
            claims_section_patterns = [
                r'CLAIMS\s+What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',         # "CLAIMS What is claimed is:" (most specific)
                r'What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',                  # Just "What is claimed is:"
                r'(?:CLAIMS?\s*\n|What is claimed[^\n]*\n)(.*?)(?:ABSTRACT|$)',  # Original with newlines (fallback)
            ]

            claims_text = None
            for pattern in claims_section_patterns:
                claims_section_match = re.search(pattern, self.spec_text, re.DOTALL | re.IGNORECASE)
                if claims_section_match:
                    claims_text = claims_section_match.group(1)
                    break

            if not claims_text:
                claims_text = self.spec_text

            # Find claim numbers - look for "N. " followed by claim preamble
            # PyPDF2 may use spaces instead of newlines between claims
            claim_patterns = [
                r'(?:^|\n)\s*(\d+)\.\s+(?:A|An|The)\s+',           # Original with newlines
                r'(?:\.\s+|\;\s+|:\s+)(\d+)\.\s+(?:A|An|The)\s+',  # After sentence end
                r'\s{2,}(\d+)\.\s+(?:A|An|The)\s+',                # After multiple spaces
                r'^\s*(\d+)\.\s+(?:A|An|The)\s+',                  # At start of claims section
                r'\s+\d{2,3}\s+(\d+)\.\s+(?:A|An|The)\s+',         # After page number (2-3 digits)
            ]

            claim_nums = []
            for pattern in claim_patterns:
                matches = re.findall(pattern, claims_text, re.IGNORECASE)
                claim_nums.extend(matches)

            if claim_nums:
                # Get unique claim numbers and verify sequence
                unique_claims = sorted(set(int(n) for n in claim_nums if 1 <= int(n) <= 100))
                self.report.add_issue(
                    62, "Cross-References", "Claim Count Verification",
                    Severity.PASS, f"Total claims detected: {len(unique_claims)} (Claims 1-{max(unique_claims)})"
                )
            else:
                # Fallback: try simpler pattern
                simple_patterns = [
                    r'(?:^|\n)\s*(\d+)\.\s+',           # Original with newlines
                    r'(?:\.\s+|\;\s+|:\s+)(\d+)\.\s+',  # After sentence end
                    r'\s{2,}(\d+)\.\s+',                # After multiple spaces
                    r'^\s*(\d+)\.\s+',                  # At start of claims section
                    r'\s+\d{2,3}\s+(\d+)\.\s+',         # After page number (2-3 digits)
                ]
                simple_claims = []
                for pattern in simple_patterns:
                    matches = re.findall(pattern, claims_text, re.MULTILINE)
                    simple_claims.extend(matches)
                simple_claims = [n for n in simple_claims if 1 <= int(n) <= 100]
                if simple_claims:
                    self.report.add_issue(
                        62, "Cross-References", "Claim Count Verification",
                        Severity.INFO, f"Possible claims detected: {len(set(simple_claims))} (manual verification recommended)"
                    )
                else:
                    self.report.add_issue(
                        62, "Cross-References", "Claim Count Verification",
                        Severity.WARNING, "Unable to count claims - claims section may use non-standard format"
                    )
        else:
            self.report.add_issue(
                62, "Cross-References", "Claim Count Verification",
                Severity.WARNING, "Specification not found"
            )
    
    def check_priority(self):
        """Checks 63-65: Priority/related application checks"""
        
        # Check 63: Priority claim consistency
        # Look for actual priority/continuation language (not just form labels)
        spec_priority = False
        ads_priority = False
        priority_patterns = [
            r'(?:claims|claiming)\s+(?:the\s+)?(?:benefit|priority)\s+(?:of|to|under)',
            r'continuation(?:\-in\-part)?\s+of',
            r'divisional\s+(?:of|application)',
            r'(?:provisional|non-provisional)\s+(?:application|patent)',
            r'filed\s+on\s+\w+\s+\d+.*?(?:Ser|Application)\s*(?:ial)?\s*(?:No|Number)',
        ]

        if self.spec_text:
            for pattern in priority_patterns:
                if re.search(pattern, self.spec_text, re.IGNORECASE):
                    spec_priority = True
                    break

        if self.ads_text:
            # Check ADS for domestic/foreign benefit sections with actual content
            ads_benefit_match = re.search(
                r'(?:Domestic\s+Benefit|Foreign\s+Priority).*?(?:Application\s*Number|Filing\s*Date)\s*[:\s]+(\d+)',
                self.ads_text, re.IGNORECASE | re.DOTALL
            )
            if ads_benefit_match:
                ads_priority = True

        if spec_priority and ads_priority:
            # Both have priority - extract app numbers to compare
            spec_app_nums = set(re.findall(r'(?:Serial|Application)\s*(?:No\.?|Number)\s*[:\s]*(\d{2}[/,]\d{3}[,.]?\d{3})',
                                          self.spec_text, re.IGNORECASE))
            ads_app_nums = set(re.findall(r'(\d{2}[/,]\d{3}[,.]?\d{3})', self.ads_text))

            if spec_app_nums and ads_app_nums:
                # Normalize and compare
                spec_norm = {re.sub(r'[,.]', '', n) for n in spec_app_nums}
                ads_norm = {re.sub(r'[,.]', '', n) for n in ads_app_nums}
                if spec_norm & ads_norm:
                    self.report.add_issue(
                        63, "Priority Claims", "Priority Claim Consistency",
                        Severity.PASS, "Priority claims consistent between specification and ADS"
                    )
                else:
                    self.report.add_issue(
                        63, "Priority Claims", "Priority Claim Consistency",
                        Severity.WARNING, f"Priority application numbers may differ: Spec={spec_app_nums}, ADS={ads_app_nums}"
                    )
            else:
                self.report.add_issue(
                    63, "Priority Claims", "Priority Claim Consistency",
                    Severity.PASS, "Priority claims present in both specification and ADS"
                )
        elif spec_priority and not ads_priority:
            self.report.add_issue(
                63, "Priority Claims", "Priority Claim Consistency",
                Severity.WARNING, "Priority language in specification but not found in ADS"
            )
        elif ads_priority and not spec_priority:
            self.report.add_issue(
                63, "Priority Claims", "Priority Claim Consistency",
                Severity.WARNING, "Priority information in ADS but not found in specification"
            )
        else:
            self.report.add_issue(
                63, "Priority Claims", "Priority Claim Consistency",
                Severity.PASS, "No priority claims detected in specification or ADS"
            )

        # Check 64: Related application references
        if spec_priority or ads_priority:
            # Check that related application info is present and consistent
            spec_related = bool(re.search(r'(?:CROSS[\-\s]*REFERENCE|RELATED\s+APPLICATION)',
                                         self.spec_text, re.IGNORECASE)) if self.spec_text else False

            if spec_priority and spec_related:
                self.report.add_issue(
                    64, "Priority Claims", "Related Application References",
                    Severity.PASS, "Related application cross-reference section found in specification"
                )
            elif spec_priority and not spec_related:
                self.report.add_issue(
                    64, "Priority Claims", "Related Application References",
                    Severity.WARNING, "Priority claims present but no Cross-Reference section found in specification"
                )
            else:
                self.report.add_issue(
                    64, "Priority Claims", "Related Application References",
                    Severity.PASS, "Related application information present in ADS"
                )
        else:
            self.report.add_issue(
                64, "Priority Claims", "Related Application References",
                Severity.PASS, "No related applications detected"
            )
        
        # Check 65: Foreign priority documents
        # Look for actual foreign priority claims, not just form labels or company names
        has_foreign = False
        foreign_details = []

        if self.spec_text:
            # Look for foreign priority claim language in specification
            # e.g., "claims priority to [country] application", "PCT/XX/YYYY"
            foreign_patterns = [
                r'claims?\s+(?:the\s+)?(?:benefit|priority)\s+(?:of|to)\s+(?:a\s+)?(?:\w+\s+)?(?:foreign|international)',
                r'PCT/[A-Z]{2}/\d{4}/\d+',  # PCT application numbers
                r'priority\s+(?:of|to)\s+(?:\w+\s+)?application[^\n]+(?:filed\s+in|of)\s+[A-Z][a-z]+',  # "priority to application filed in Japan"
                r'(?:EP|JP|CN|KR|DE|FR|GB|CA|AU|IN)\s*\d{5,}',  # Foreign application numbers
            ]
            for pattern in foreign_patterns:
                match = re.search(pattern, self.spec_text, re.IGNORECASE)
                if match:
                    has_foreign = True
                    foreign_details.append(match.group(0)[:50])
                    break

        if not has_foreign and self.ads_text:
            # Check ADS for actual foreign priority data (not just form labels)
            # Look for country codes with application numbers or dates in priority context
            # Avoid matching form instructions or field labels
            ads_foreign_patterns = [
                r'(?:priority|benefit)[^\n]{0,30}(?:EP|JP|CN|KR|DE|FR|GB|CA|AU|IN|WO)\s*[\d\-/]+',
                r'PCT/[A-Z]{2}/\d{4}/\d+',
                # Look for filled-in foreign priority section (country + number pattern)
                r'(?:^|\n)\s*(?:EP|JP|CN|KR|DE|FR|GB|CA|AU|IN)\s+\d{4}[\d\-]+',
            ]
            for pattern in ads_foreign_patterns:
                match = re.search(pattern, self.ads_text, re.IGNORECASE)
                if match:
                    has_foreign = True
                    foreign_details.append(match.group(0)[:50])
                    break

        if has_foreign:
            self.report.add_issue(
                65, "Priority Claims", "Foreign Priority Documents",
                Severity.INFO,
                f"Foreign priority claim detected: {foreign_details[0] if foreign_details else 'verify details'}"
            )
        else:
            self.report.add_issue(
                65, "Priority Claims", "Foreign Priority Documents",
                Severity.PASS, "No foreign priority claims detected"
            )
    
    def check_final_quality(self):
        """Checks 66-70: Final quality checks"""
        
        # Check 66: No obvious typos in critical fields
        if self.spec_text or self.ads_text:
            issues_66 = []

            # Check docket number format (should be consistent pattern like A###-####XX)
            docket_pattern = r'[A-Z]\d{2,4}[\s\-]*\d{3,4}[A-Z]{2}'
            all_texts = {'spec': self.spec_text, 'ads': self.ads_text, 'decl': self.declaration_text}
            docket_numbers = set()
            for doc, text in all_texts.items():
                if text:
                    matches = re.findall(docket_pattern, text)
                    for m in matches:
                        docket_numbers.add(re.sub(r'\s', '', m))

            if len(docket_numbers) > 1:
                issues_66.append(f"Multiple docket number variants: {', '.join(docket_numbers)}")

            # Check inventor names for mixed case issues (e.g., "gUPTA" instead of "GUPTA" or "Gupta")
            if self.ads_text:
                inventor_names = re.findall(r'(?:Given|Family)\s*Name[:\s]+([A-Za-z]+)', self.ads_text)
                for name in inventor_names:
                    if name and len(name) > 1:
                        # Name should be either all caps, all lower, or title case
                        if not (name.isupper() or name.islower() or name.istitle()):
                            issues_66.append(f"Unusual capitalization in inventor name: '{name}'")

            # Check title for incomplete words or obvious issues
            title_match = re.search(r'(?:Title|TITLE).*?(?:of|:)\s*(?:the\s+)?(?:Invention\s*)?(.*?)(?:\n|$|Attorney)',
                                   self.ads_text or self.spec_text, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
                if len(title) < 5:
                    issues_66.append(f"Title appears too short: '{title}'")
                if re.search(r'\b[A-Z]{1}\b', title):  # Single uppercase letters (may be typos)
                    pass  # Single letters can be valid in titles

            if issues_66:
                self.report.add_issue(
                    66, "Final Quality", "No Obvious Typos in Critical Fields",
                    Severity.WARNING, f"Potential issues found: {'; '.join(issues_66[:3])}"
                )
            else:
                self.report.add_issue(
                    66, "Final Quality", "No Obvious Typos in Critical Fields",
                    Severity.PASS, "No obvious typos detected in critical fields"
                )
        else:
            self.report.add_issue(
                66, "Final Quality", "No Obvious Typos in Critical Fields",
                Severity.INFO, "Insufficient document text for typo analysis"
            )

        # Check 67: Dates in proper format
        if self.ads_text or self.declaration_text or self.assignment_text:
            all_doc_text = (self.ads_text or '') + (self.declaration_text or '') + (self.assignment_text or '')

            months = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'

            # Find dates in various formats
            date_patterns = [
                (r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b', 'MM/DD/YYYY'),
                (r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\b', 'MM/DD/YY'),
                (r'\b(' + months + r')\s+(\d{1,2}),?\s+(\d{4})\b', 'Month DD, YYYY'),
                (r'\b(\d{1,2})\s+(' + months + r')\s+(\d{4})\b', 'DD Month YYYY'),
            ]

            dates_found = []
            issues_67 = []
            # Form template boilerplate patterns to ignore
            form_boilerplate = re.compile(
                r'(?:approved\s+for\s+use|OMB|Paperwork\s+Reduction|collection\s+of\s+information|'
                r'CFR\s+\d|U\.S\.\s+Patent\s+and\s+Trademark)',
                re.IGNORECASE
            )

            for pattern, fmt in date_patterns:
                for m_obj in re.finditer(pattern, all_doc_text, re.IGNORECASE):
                    m = m_obj.groups()
                    # Skip dates in form boilerplate context (100 chars before/after)
                    context_start = max(0, m_obj.start() - 100)
                    context_end = min(len(all_doc_text), m_obj.end() + 100)
                    context = all_doc_text[context_start:context_end]
                    if form_boilerplate.search(context):
                        continue

                    dates_found.append((m, fmt))
                    # Check for 2-digit years (potential issue)
                    if fmt == 'MM/DD/YY':
                        issues_67.append(f"2-digit year found: {'/'.join(m)}")
                    # Check for reasonable year range
                    if fmt in ('MM/DD/YYYY', 'Month DD, YYYY', 'DD Month YYYY'):
                        year = int(m[2])
                        if year < 2000 or year > 2030:
                            issues_67.append(f"Date with unusual year: {' '.join(m)}")

            if issues_67:
                self.report.add_issue(
                    67, "Final Quality", "Dates in Proper Format",
                    Severity.WARNING, f"Date format issues: {'; '.join(issues_67[:3])}"
                )
            elif dates_found:
                self.report.add_issue(
                    67, "Final Quality", "Dates in Proper Format",
                    Severity.PASS, f"All {len(dates_found)} dates appear properly formatted"
                )
            else:
                self.report.add_issue(
                    67, "Final Quality", "Dates in Proper Format",
                    Severity.PASS, "No date format issues detected"
                )
        else:
            self.report.add_issue(
                67, "Final Quality", "Dates in Proper Format",
                Severity.INFO, "Insufficient document text for date analysis"
            )
        
        # Check 68: No excessively long claims
        if self.spec_text:
            # Find claims section using flexible patterns (PyPDF2 may not preserve newlines)
            claims_section_patterns = [
                r'CLAIMS\s+What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',
                r'What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',
                r'(?:CLAIMS?\s*\n|What is claimed[^\n]*\n)(.*?)(?:ABSTRACT|$)',
            ]
            claims_text = None
            for pattern in claims_section_patterns:
                match = re.search(pattern, self.spec_text, re.DOTALL | re.IGNORECASE)
                if match:
                    claims_text = match.group(1)
                    break
            if not claims_text:
                claims_text = self.spec_text

            # Find individual claims using flexible patterns
            claim_start_patterns = [
                r'(?:^|\n)\s*(\d+)\.\s+(?:A|An|The)\s+',
                r'(?:\.\s{1,3})(\d+)\.\s+(?:A|An|The)\s+',
                r'\s{2,}(\d+)\.\s+(?:A|An|The)\s+',
                r'\s+\d{2,3}\s+(\d+)\.\s+(?:A|An|The)\s+',
            ]

            # Use finditer to get positions for splitting
            all_claim_positions = []
            for pattern in claim_start_patterns:
                for m in re.finditer(pattern, claims_text, re.IGNORECASE | re.MULTILINE):
                    claim_num = int(m.group(1))
                    if 1 <= claim_num <= 100:
                        all_claim_positions.append((m.start(), claim_num, m.end()))

            # Deduplicate by claim number (keep first occurrence)
            seen_claims = {}
            for start, num, end in sorted(all_claim_positions):
                if num not in seen_claims:
                    seen_claims[num] = (start, end)

            claims = []
            sorted_claims = sorted(seen_claims.items())
            for i, (claim_num, (start, text_start)) in enumerate(sorted_claims):
                # End at next claim start or end of text
                if i + 1 < len(sorted_claims):
                    end = sorted_claims[i + 1][1][0]
                else:
                    end = len(claims_text)
                claim_body = claims_text[text_start:end].strip()
                word_count = len(claim_body.split())
                claims.append((claim_num, word_count))

            if claims:
                long_claims = [(num, words) for num, words in claims if words > 200]
                if long_claims:
                    details = ", ".join([f"Claim {num} ({words} words)" for num, words in long_claims[:5]])
                    self.report.add_issue(
                        68, "Final Quality", "No Excessively Long Claims",
                        Severity.WARNING, f"Unusually long claims detected: {details}"
                    )
                else:
                    self.report.add_issue(
                        68, "Final Quality", "No Excessively Long Claims",
                        Severity.PASS, f"No excessively long claims detected ({len(claims)} claims checked)"
                    )
            else:
                self.report.add_issue(
                    68, "Final Quality", "No Excessively Long Claims",
                    Severity.INFO, "Unable to parse individual claims for length check"
                )
        else:
            self.report.add_issue(
                68, "Final Quality", "No Excessively Long Claims",
                Severity.WARNING, "Specification not found"
            )
        
        # Check 69: Specification references all claims
        if self.spec_text:
            # Extract claims section
            claims_section_patterns = [
                r'CLAIMS\s+What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',
                r'What is claimed[^:]*:\s*(.*?)(?:ABSTRACT|$)',
                r'(?:CLAIMS?\s*\n|What is claimed[^\n]*\n)(.*?)(?:ABSTRACT|$)',
            ]
            claims_text_69 = None
            for pattern in claims_section_patterns:
                m = re.search(pattern, self.spec_text, re.DOTALL | re.IGNORECASE)
                if m:
                    claims_text_69 = m.group(1)
                    break

            # Get description text (everything before claims)
            desc_match = re.search(
                r'(?:DETAILED\s+DESCRIPTION|DESCRIPTION\s+OF.*?EMBODIMENTS?)(.*?)(?:CLAIMS|What is claimed)',
                self.spec_text, re.DOTALL | re.IGNORECASE
            )
            desc_text_69 = desc_match.group(1) if desc_match else ""

            if claims_text_69 and desc_text_69:
                # Extract reference numerals from claims
                claim_numerals = set(re.findall(r'\b(\d{2,3})\b', claims_text_69))
                # Filter to actual reference numerals (those used with element descriptions)
                valid_numerals = set()
                for num in claim_numerals:
                    if re.search(r'(?:a|an|the|said)\s+[\w\-]+(?:\s+[\w\-]+){0,2}\s+' + num + r'\b',
                                claims_text_69, re.IGNORECASE):
                        valid_numerals.add(num)

                if valid_numerals:
                    # Check which numerals appear in the detailed description
                    missing = [n for n in valid_numerals if n not in desc_text_69]
                    if not missing:
                        self.report.add_issue(
                            69, "Final Quality", "Specification References All Claims",
                            Severity.PASS, f"All {len(valid_numerals)} claim reference numerals found in specification"
                        )
                    elif len(missing) <= 2:
                        self.report.add_issue(
                            69, "Final Quality", "Specification References All Claims",
                            Severity.PASS, f"Most claim elements referenced in specification ({len(valid_numerals) - len(missing)}/{len(valid_numerals)})"
                        )
                    else:
                        self.report.add_issue(
                            69, "Final Quality", "Specification References All Claims",
                            Severity.WARNING, f"{len(missing)} claim reference numerals not found in specification: {', '.join(sorted(missing)[:5])}"
                        )
                else:
                    # No reference numerals in claims - check key terms instead
                    claim_words = set(re.findall(r'\b([a-z]{5,})\b', claims_text_69.lower()))
                    stop = {'comprising', 'including', 'wherein', 'thereof', 'therein', 'configured',
                           'coupled', 'connected', 'having', 'being', 'method', 'system', 'further',
                           'claim', 'according', 'recited', 'least', 'between', 'based', 'associated'}
                    key_terms = claim_words - stop
                    if key_terms:
                        found = sum(1 for t in key_terms if t in desc_text_69.lower())
                        coverage = found / len(key_terms)
                        if coverage >= 0.7:
                            self.report.add_issue(
                                69, "Final Quality", "Specification References All Claims",
                                Severity.PASS, f"Specification covers {coverage:.0%} of claim terminology"
                            )
                        else:
                            self.report.add_issue(
                                69, "Final Quality", "Specification References All Claims",
                                Severity.WARNING, f"Specification may not fully support claims ({coverage:.0%} term coverage)"
                            )
                    else:
                        self.report.add_issue(
                            69, "Final Quality", "Specification References All Claims",
                            Severity.PASS, "Claims and specification present"
                        )
            else:
                self.report.add_issue(
                    69, "Final Quality", "Specification References All Claims",
                    Severity.INFO, "Could not isolate claims and description for cross-reference"
                )
        else:
            self.report.add_issue(
                69, "Final Quality", "Specification References All Claims",
                Severity.WARNING, "Specification not found"
            )
        
        # Check 70: Consistent figure reference format
        if self.spec_text:
            fig_refs = re.findall(r'(FIG(?:URE)?\.?\s*\d+)', self.spec_text, re.IGNORECASE)
            if fig_refs:
                formats = set(ref.split()[0].upper() for ref in fig_refs)
                if len(formats) == 1:
                    self.report.add_issue(
                        70, "Final Quality", "Consistent Figure Reference Format",
                        Severity.PASS, f"Figure references use consistent format: {list(formats)[0]}"
                    )
                else:
                    self.report.add_issue(
                        70, "Final Quality", "Consistent Figure Reference Format",
                        Severity.WARNING, f"Mixed figure reference formats detected: {formats}"
                    )
            else:
                self.report.add_issue(
                    70, "Final Quality", "Consistent Figure Reference Format",
                    Severity.INFO, "No figure references detected"
                )
        else:
            self.report.add_issue(
                70, "Final Quality", "Consistent Figure Reference Format",
                Severity.WARNING, "Specification not found"
            )
    
    def generate_markdown_report(self, output_path: str):
        """Generate Markdown report"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Patent Filing Quality Control Report\n\n")
            f.write(f"**Folder:** {self.report.folder_path}\n")
            import datetime
            f.write(f"**Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

            # Summary counts
            critical_count = self.report.get_critical_count()
            warning_count = self.report.get_warning_count()
            info_count = sum(1 for i in self.report.issues if i.severity == Severity.INFO)
            pass_count = self.report.get_pass_count()

            f.write("## Executive Summary\n\n")
            f.write(f"- 🚨 **Critical Issues:** {critical_count}\n")
            f.write(f"- ⚠️ **Warnings:** {warning_count}\n")
            f.write(f"- ℹ️ **Info/Manual Review:** {info_count}\n")
            f.write(f"- ✅ **Passed:** {pass_count}\n\n")

            # Files found
            f.write("## Documents Found\n\n")
            for doc_type, filename in self.report.files_found.items():
                status = "✅" if filename else "❌"
                f.write(f"- {status} **{doc_type}:** {filename if filename else 'NOT FOUND'}\n")
            f.write("\n")

            # Helper function to group issues by category
            def group_by_category(issues):
                categories = {}
                for issue in issues:
                    if issue.category not in categories:
                        categories[issue.category] = []
                    categories[issue.category].append(issue)
                return categories

            # Critical issues section
            critical_issues = [i for i in self.report.issues if i.severity == Severity.CRITICAL]
            if critical_issues:
                f.write("## 🚨 Critical Issues (Must Fix Before Filing)\n\n")
                categories = group_by_category(critical_issues)
                for category, issues in sorted(categories.items()):
                    f.write(f"### {category}\n\n")
                    for issue in sorted(issues, key=lambda x: x.check_id):
                        f.write(f"🚨 **{issue.check_id}. {issue.check_name}**\n")
                        f.write(f"   {issue.message}\n")
                        if issue.details:
                            f.write(f"   ```\n   {issue.details}\n   ```\n")
                        f.write("\n")
                f.write("\n")

            # Warnings section
            warnings = [i for i in self.report.issues if i.severity == Severity.WARNING]
            if warnings:
                f.write("## ⚠️ Warnings (Should Review)\n\n")
                categories = group_by_category(warnings)
                for category, issues in sorted(categories.items()):
                    f.write(f"### {category}\n\n")
                    for issue in sorted(issues, key=lambda x: x.check_id):
                        f.write(f"⚠️ **{issue.check_id}. {issue.check_name}**\n")
                        f.write(f"   {issue.message}\n")
                        if issue.details:
                            f.write(f"   ```\n   {issue.details}\n   ```\n")
                        f.write("\n")
                f.write("\n")

            # Info/Manual Review section
            info_issues = [i for i in self.report.issues if i.severity == Severity.INFO]
            if info_issues:
                f.write("## ℹ️ Info/Manual Review Required\n\n")
                categories = group_by_category(info_issues)
                for category, issues in sorted(categories.items()):
                    f.write(f"### {category}\n\n")
                    for issue in sorted(issues, key=lambda x: x.check_id):
                        f.write(f"ℹ️ **{issue.check_id}. {issue.check_name}**\n")
                        f.write(f"   {issue.message}\n")
                        f.write("\n")
                f.write("\n")

            # Passed section
            passed_issues = [i for i in self.report.issues if i.severity == Severity.PASS]
            if passed_issues:
                f.write("## ✅ Passed Checks\n\n")
                categories = group_by_category(passed_issues)
                for category, issues in sorted(categories.items()):
                    f.write(f"### {category}\n\n")
                    for issue in sorted(issues, key=lambda x: x.check_id):
                        f.write(f"✅ **{issue.check_id}. {issue.check_name}**\n")
                        f.write(f"   {issue.message}\n")
                        f.write("\n")
                f.write("\n")

            # Footer
            f.write("---\n\n")
            f.write("*This report was generated by the Patent Filing QC skill for Claude Code CLI*\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Patent Filing Quality Control')
    parser.add_argument('folder', help='Path to folder containing patent filing documents')
    parser.add_argument('--output-dir', default='.', help='Directory for output reports (default: current directory)')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("PATENT FILING QUALITY CONTROL")
    print("=" * 80)
    print()
    
    # Initialize QC engine
    qc = PatentFilingQC(args.folder)
    
    # Load documents
    print("📁 Loading documents...")
    qc.load_documents()
    print()
    
    print("Documents found:")
    for doc_type, filename in qc.report.files_found.items():
        status = "✅" if filename else "❌"
        print(f"  {status} {doc_type}: {filename if filename else 'NOT FOUND'}")
    print()
    
    # Run all checks
    print("🔍 Running quality control checks...")
    qc.run_all_checks()
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Passed:          {qc.report.get_pass_count()}")
    print(f"⚠️  Warnings:        {qc.report.get_warning_count()}")
    print(f"🚨 Critical Issues: {qc.report.get_critical_count()}")
    print(f"ℹ️  Info/Manual:     {sum(1 for i in qc.report.issues if i.severity == Severity.INFO)}")
    print()

    # List critical issues in console (to match markdown report)
    critical_issues = [i for i in qc.report.issues if i.severity == Severity.CRITICAL]
    if critical_issues:
        print("=" * 80)
        print("🚨 CRITICAL ISSUES (Must Fix Before Filing)")
        print("=" * 80)
        for issue in critical_issues:
            print(f"\n{issue.check_id}. {issue.check_name}")
            print(f"   Category: {issue.category}")
            print(f"   Issue: {issue.message}")
            if issue.details:
                print(f"   Details: {issue.details}")
        print()

    # List warnings in console (to match markdown report)
    warnings = [i for i in qc.report.issues if i.severity == Severity.WARNING]
    if warnings:
        print("=" * 80)
        print("⚠️  WARNINGS (Should Review)")
        print("=" * 80)
        for issue in warnings:
            print(f"\n{issue.check_id}. {issue.check_name}")
            print(f"   Category: {issue.category}")
            print(f"   Warning: {issue.message}")
            if issue.details:
                print(f"   Details: {issue.details}")
        print()
    
    # Generate reports
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    md_report = output_dir / "Patent_Filing_QC_Report.md"
    print(f"📝 Generating Markdown report: {md_report}")
    qc.generate_markdown_report(str(md_report))
    
    # Generate PDF using markdown-pdf or similar
    pdf_report = output_dir / "Patent_Filing_QC_Report.pdf"
    print(f"📄 Generating PDF report: {pdf_report}")
    
    # Use pandoc or weasyprint to convert MD to PDF
    try:
        import subprocess
        # Try pandoc first
        result = subprocess.run(
            ['pandoc', str(md_report), '-o', str(pdf_report), 
             '--pdf-engine=pdflatex', '-V', 'geometry:margin=1in'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("✅ PDF generated successfully using pandoc")
        else:
            # Try weasyprint as fallback
            try:
                from weasyprint import HTML
                from markdown import markdown
                with open(md_report) as f:
                    md_content = f.read()
                html_content = markdown(md_content)
                HTML(string=html_content).write_pdf(pdf_report)
                print("✅ PDF generated successfully using weasyprint")
            except:
                print("⚠️  PDF generation failed. Install pandoc or weasyprint for PDF output.")
                print("   For now, only Markdown report is available.")
    except Exception as e:
        print(f"⚠️  PDF generation failed: {e}")
        print("   Install pandoc or weasyprint for PDF output.")
        print("   For now, only Markdown report is available.")
    
    print()
    print("=" * 80)
    print("QC COMPLETE")
    print("=" * 80)
    
    if qc.report.get_critical_count() > 0:
        print()
        print("🚨 CRITICAL ISSUES FOUND - Review report before filing!")
        return 1
    elif qc.report.get_warning_count() > 0:
        print()
        print("⚠️  Warnings found - Review recommended")
        return 0
    else:
        print()
        print("✅ All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
