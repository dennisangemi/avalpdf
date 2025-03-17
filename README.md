# avalpdf - PDF Accessibility Validator

A command-line tool for validating PDF accessibility, analyzing document structure, and generating detailed reports.

## Features

<details>
<summary><strong>Document structure analysis and support</strong></summary>

- Document structure analysis 
- Support for both local and remote PDF files
</details>

<details>
<summary><strong>Document tags and metadata validation</strong></summary>

- Document tagging status
- Title presence
- Language declaration (Italian)
</details>

<details>
<summary><strong>Heading hierarchy validation</strong></summary>

- H1 presence
- Correct heading levels sequence
</details>

<details>
<summary><strong>Figure alt text validation</strong></summary>

- Missing alternative text detection
- Complex or problematic alt text patterns
</details>

<details>
<summary><strong>Tables structure validation</strong></summary>

- Header presence and proper structure
- Empty cells detection
- Duplicate headers check
- Multiple header rows warning
- Empty tables detection
</details>

<details>
<summary><strong>Lists structure validation</strong></summary>

- Proper list tagging
- Detection of untagged lists (consecutive paragraphs with bullets/numbers)
- Misused list types (numbered items in unordered lists)
- List hierarchy consistency
</details>

<details>
<summary><strong>Links validation</strong></summary>

- Detection of non-descriptive links
- Raw URL text warnings
- Email and institutional domain exceptions
</details>

<details>
<summary><strong>Formatting issues detection</strong></summary>

- Excessive underscores (used for underlining)
- Spaced capital letters (like "T E S T")
- Extra spaces used for layout (3+ consecutive spaces)
</details>

<details>
<summary><strong>Empty elements detection</strong></summary>

- Empty paragraphs
- Whitespace-only elements
- Empty headings
- Empty spans
- Empty table cells
</details>

<details>
<summary><strong>Output formats</strong></summary>

- Detailed JSON structure
- Simplified JSON
- Accessibility validation report
- Console reports with color-coded structure visualization
</details>

<details>
<summary><strong>Scoring and reporting</strong></summary>

- Weighted scoring system based on accessibility criteria
- Detailed issue categorization (issues, warnings, successes)
</details>

## Installation

Using `pip`
```bash
pip install avalpdf
```

Or `uv`
```bash
uv tool install avalpdf
```

### Updates
Using `pip`
```bash
pip install avalpdf --upgrade
```

Or `uv`
```bash
uv tool install avalpdf --upgrade
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

# Display version information
avalpdf --version
```

Command Line Options
* `--full`: Save full JSON structure
* `--simple`: Save simplified JSON structure
* `--report`: Save validation report
* `--output-dir`, `-o`: Specify output directory
* `--show-structure`: Display document structure
* `--show-validation`: Display validation results
* `--quiet`, `-q`: Suppress console output
* `--rich`: Use enhanced visual formatting for document structure
* `--tree`: Use tree view instead of panel view with Rich formatting
* `--version`, `-v`: Display the version number and exit

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

## Local development

```sh
uv venv .test
source .test/bin/activate
uv pip install -e . --upgrade
```