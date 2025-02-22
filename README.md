# avalpdf - PDF Accessibility Validator

A command-line tool for validating PDF accessibility, analyzing document structure, and generating detailed reports.

## Features

- Full PDF accessibility validation
- Document structure analysis
- Validation of:
  - Document tags and metadata
  - Heading hierarchy
  - Table structure and headers
  - Figure alt text
  - Empty elements
  - Lists (ordered and unordered)
- Multiple output formats (JSON, console reports)

## Requirements

- Python 3.6+
- PDFix SDK

## Installation

> ⚠️ **Note**: The installation procedure is currently a work in progress and may not be fully stable. Improvements are being made to make the installation process more robust.

1. Install PDFix SDK:
```bash
pip install pdfix-sdk
```

2. Download and install avalpdf:
```bash
sudo sh -c 'wget https://raw.githubusercontent.com/dennisangemi/avalpdf/main/avalpdf -O /usr/local/bin/avalpdf && chmod +x /usr/local/bin/avalpdf'
```

## Usage
After installation, you can run avalpdf from any directory:

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
* `--show-all`: Show all information
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
