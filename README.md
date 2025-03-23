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
- Consolidated batch report for multiple files
- Console reports with color-coded structure visualization
</details>

<details>
<summary><strong>Scoring and reporting</strong></summary>

- Weighted scoring system based on accessibility criteria
- Detailed issue categorization (issues, warnings, successes)
</details>

<details>
<summary><strong>Batch processing</strong></summary>

- Process multiple files with glob patterns (e.g., `*.pdf`)
- Directory scanning
- Concise progress display for multiple files
- Consolidated batch report with aggregated statistics
- Parallel processing for faster validation on multi-core systems
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

# Display version information
avalpdf --version
```

## Multi-file Analysis

avalpdf supports analyzing multiple PDF files in a single command using parallel processing:

```sh
# Multiple files specified directly
avalpdf file1.pdf file2.pdf file3.pdf

# Using wildcard pattern (use quotes on some shells)
avalpdf "*.pdf"

# Process all PDFs in a specific directory
avalpdf "reports/quarterly/*.pdf"

# Analyze all PDFs in the current directory
avalpdf *.pdf

# Specify a directory to scan
avalpdf /path/to/documents/

# Mix of patterns and specific files
avalpdf annual_report.pdf "monthly/*.pdf" project_docs/specs.pdf
```

When processing multiple files, avalpdf automatically uses parallel processing to take advantage of multi-core systems, significantly improving performance for large batches of documents.

When using wildcards on Unix/Linux shells, you may need to quote the pattern if you want avalpdf to handle the expansion rather than the shell.

### Multi-file Output

When analyzing multiple files, avalpdf displays a concise progress view:

```
[1/5] ✅ document1.pdf: 0 issues, 2 warnings
[2/5] ❌ document2.pdf: 3 issues, 5 warnings
[3/5] ⚠️ document3.pdf: Error - Failed to open PDF
[4/5] ✅ document4.pdf: 0 issues, 0 warnings
[5/5] ❌ document5.pdf: 2 issues, 1 warnings

📊 Batch Processing Summary:
  • Total files processed: 5
  • Files with issues: 2
  • Total issues: 5
  • Total warnings: 8
  • Average accessibility score: 82.5%

✨ Batch processing complete!
```

By default, a consolidated batch report is saved when processing multiple files. This JSON file contains:
- Analysis results for each file
- Metadata and accessibility score for each file
- Aggregated statistics across all files
- Timestamp of the analysis

To specify the output location for the batch report, you have multiple options:

```sh
# Specify output directory (report will have a timestamp-based name)
avalpdf *.pdf -o /path/to/output/

# Specify exact filename (including path)
avalpdf *.pdf -o /path/to/output/report.json

# Alternative: specify output directory and custom filename
avalpdf *.pdf -o /path/to/output --batch-report=my_report.json
```

When `-o` points to a file ending with `.json`, it will be used as the exact batch report path. Otherwise, it's treated as a directory.

### Analyzing Batch Reports

The batch report JSON file can be analyzed with command-line tools to extract useful information. For example, you can convert the batch report to CSV format for analysis in spreadsheet software:

```sh
avalpdf_batch_report_20250323_012754.json jq '.files[] | {filename, poducer: .metadata.producer, creator: .metadata.creator, standard: .metadata.standard, n_issues: .issues_count, n_warnings: .warnings_count, accessibility_score}' | mlr --j2c cat | vd
```

This command uses:
- `jq` to extract specific fields from each file entry
- `miller` (`mlr`) to convert JSON to CSV
- `visidata` (`vd`) to view and analyze the data interactively

You can modify the jq query to extract different fields based on your analysis needs.

### Common Multi-file Scenarios

```sh
# Analyze all PDFs in a directory, save individual reports
avalpdf "reports/*.pdf" --report

# Analyze multiple files silently and save batch report
avalpdf file1.pdf file2.pdf file3.pdf --quiet

# Process files in different directories
avalpdf "team1/*.pdf" "team2/*.pdf" "shared/*.pdf"

# Analyze all PDFs in a directory and subdirectories
# (use find in Unix/Linux or dir /s in Windows to collect paths)
find . -name "*.pdf" | xargs avalpdf
```

## Command Line Options
* `--full`: Save full JSON structure
* `--simple`: Save simplified JSON structure
* `--report`: Save validation report
* `--batch-report[=FILENAME]`: Save consolidated batch report when processing multiple files. Optionally specify filename
* `--output-dir`, `-o`: Specify output directory
* `--show-structure`: Display document structure
* `--show-validation`: Display validation results
* `--quiet`, `-q`: Suppress console output
* `--rich`: Use enhanced visual formatting for document structure
* `--tree`: Use tree view instead of panel view with Rich formatting
* `--version`, `-v`: Display the version number and exit

## Examples
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
avalpdf *.pdf
```

5. Analyze directory:
```sh
avalpdf documents/
```

6. Process specific file pattern and save reports in output directory:
```sh
avalpdf "invoices/2023_*.pdf" -o validation_results --report
```

7. Quiet batch processing:
```sh
avalpdf *.pdf --quiet --batch-report -o reports
```

## Batch Report Format

The consolidated batch report is saved as a JSON file with this structure:

```json
{
  "timestamp": "2023-05-20T14:30:45.123456",
  "formatted_date": "2023-05-20 14:30:45",
  "summary": {
    "total_files": 3,
    "files_with_issues": 1,
    "total_issues": 3,
    "total_warnings": 7,
    "average_accessibility_score": 70.25,
    "successful_files": 2,
    "failed_files": 1
  },
  "files": [
    {
      "filename": "document1.pdf",
      "path": "/path/to/document1.pdf",
      "index": 1,
      "metadata": {
        "title": "Sample Document",
        "tagged": "true",
        "lang": "it",
        "num_pages": "10"
      },
      "issues_count": 0,
      "warnings_count": 2,
      "accessibility_score": 95.5,
      "success": true,
      "has_issues": false
    },
    {
      "filename": "document2.pdf",
      "path": "/path/to/document2.pdf",
      "index": 2,
      "metadata": {
        "title": "Another Document",
        "tagged": "false",
        "lang": "",
        "num_pages": "5"
      },
      "issues_count": 3,
      "warnings_count": 5,
      "accessibility_score": 45.0,
      "success": true,
      "has_issues": true
    },
    {
      "filename": "document3.pdf",
      "path": "/path/to/document3.pdf",
      "index": 3,
      "success": false,
      "error": "Failed to open PDF",
      "issues_count": 0,
      "warnings_count": 0,
      "accessibility_score": 0.0
    }
  ]
}
```

This structured format makes it easy to:
- Sort files by name, accessibility score, or issues count
- Filter files with issues or errors
- Process results using data analysis tools
- Generate custom reports from the consolidated data

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