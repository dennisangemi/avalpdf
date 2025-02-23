# avalpdf - PDF Accessibility Validator

A command-line tool for validating PDF accessibility, analyzing document structure, and generating detailed reports.

## Features

- Document structure analysis 
- Support for both local and remote PDF files
- Validation of:
  - Document tags and metadata:
    - Document tagging status
    - Title presence
    - Language declaration
  - Heading hierarchy:
    - H1 presence
    - Correct heading levels sequence
  - Figure alt text:
    - Missing alternative text detection
  - Tables structure:
    - Header presence and proper structure
    - Empty cells detection
    - Duplicate headers check
    - Multiple header rows warning
    - Empty tables detection
  - Lists structure:
    - Proper list tagging
    - Detection of untagged lists (consecutive paragraphs with bullets/numbers)
    - Misused list types (numbered items in unordered lists)
    - List hierarchy consistency
  - Formatting issues:
    - Excessive underscores (used for underlining)
    - Spaced capital letters (like "T E S T")
    - Extra spaces used for layout
  - Empty elements:
    - Empty paragraphs
    - Whitespace-only elements
    - Empty headings
    - Empty table cells
- Multiple output formats (JSON, console reports)

## Installation

```bash
pip install avalpdf
```

## Usage
After installation, you can run avalpdf from any directory.

### Quick start
Simply run
```sh
avalpdf thesis.pdf
```

or 

```sh
avalpdf https://example.com/document.pdf
```

to get a report like this

![accessibility report](https://github.com/user-attachments/assets/6f9fc73e-7bcc-4e8a-8c51-0000e11f18cf)

and a preview of the structure

![pdf structure preview](https://github.com/user-attachments/assets/d09266bc-39af-4e02-b477-55cbf72a95d5)


### Details

```sh
# Basic validation with console output
avalpdf document.pdf

# Complete analysis with all outputs
avalpdf document.pdf --full --simple --report

# Save reports to specific directory
avalpdf document.pdf -o /path/to/output --report --simple

# Show document structure only
avalpdf document.pdf --show-structure
```

Command Line Options
* `--full`: Save full JSON structure
* `--simple`: Save simplified JSON structure
* `--report`: Save validation report
* `--output-dir`, `-o`: Specify output directory
* `--show-structure`: Display document structure
* `--show-validation`: Display validation results
* `--quiet`, `-q`: Suppress console output

Examples
1. Quick accessibility check:
```sh
avalpdf thesis.pdf
```

2. Generate all reports:
```sh
avalpdf report.pdf --full --simple --report -o ./analysis
```

3. Silent operation with report generation:
```sh
avalpdf document.pdf --report -q
```

4. Analyze multiple files:
```sh
for file in *.pdf; do avalpdf "$file" --report --quiet; done
```

## Validation Output
The tool provides three types of findings:

* ✅ Successes: Correctly implemented accessibility features
* ⚠️ Warnings: Potential issues that need attention
* ❌ Issues: Problems that must be fixed

Report Format
```json
{
  "validation_results": {
    "issues": ["..."],
    "warnings": ["..."],
    "successes": ["..."]
  }
}
```
## License
MIT License

## Support
For issues or suggestions:

* Open an issue on GitHub
* Provide the PDF file (if possible) and the complete error message
* Include the command you used and your operating system information
