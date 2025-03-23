#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import sys
from pdfixsdk import *
import ctypes
from typing import Dict, List, Tuple, Optional, Union
import tempfile
import urllib.request
import urllib.parse
import glob
import os
import concurrent.futures
from multiprocessing import cpu_count
import datetime

from avalpdf.converter import pdf_to_json
from avalpdf.extractor import extract_content, create_simplified_json
from avalpdf.formatter import print_formatted_content, COLOR_GREEN, COLOR_RED, COLOR_ORANGE, COLOR_PURPLE, COLOR_BLUE, COLOR_RESET
from avalpdf.utils import download_pdf, is_url
from avalpdf.validator import AccessibilityValidator
from avalpdf.version import __version__

# Import Rich formatter conditionally to allow for fallback if not installed
try:
    from avalpdf.rich_formatter import display_document_structure, display_document_structure_tree
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

def expand_file_paths(inputs: List[str]) -> List[str]:
    """
    Expand wildcards, directory paths, and regular file paths into a list of PDF files.
    
    Args:
        inputs: List of file paths, wildcards, or directory paths
        
    Returns:
        List of absolute paths to PDF files
    """
    pdf_files = []
    
    for input_path in inputs:
        if os.path.isdir(input_path):
            # If input is a directory, find all PDFs in it
            dir_pdfs = glob.glob(os.path.join(input_path, "*.pdf"))
            pdf_files.extend(dir_pdfs)
        elif '*' in input_path or '?' in input_path:
            # If input contains wildcards, expand them
            matched_files = glob.glob(input_path)
            # Filter to only include PDF files
            for file in matched_files:
                if file.lower().endswith('.pdf') and os.path.isfile(file):
                    pdf_files.append(file)
        elif input_path.lower().endswith('.pdf'):
            # Add direct PDF file references
            pdf_files.append(input_path)
        elif is_url(input_path):
            # Keep URLs as they are - they'll be processed later
            pdf_files.append(input_path)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_files = []
    for file in pdf_files:
        abs_path = os.path.abspath(file)
        if abs_path not in seen and not is_url(file):
            seen.add(abs_path)
            unique_files.append(abs_path)
        elif is_url(file) and file not in seen:
            seen.add(file)
            unique_files.append(file)
    
    return unique_files

def analyze_pdf(pdf_path: str, options: dict) -> Dict:
    """
    Analyze a PDF file with configurable outputs
    
    Returns:
        Dictionary with validation results for summary and multi-file reporting
    """
    result = {
        "file": pdf_path,
        "metadata": {},
        "issues": [],
        "warnings": [],
        "score": 0
    }
    
    tmp_path = None
    cleanup_needed = False
    
    try:
        # Handle URL if needed
        if is_url(pdf_path):
            tmp_path = download_pdf(pdf_path)
            pdf_path_to_analyze = str(tmp_path)
            cleanup_needed = True
        else:
            pdf_path_to_analyze = pdf_path
            
        # Setup output directory
        output_path = Path(options['output_path']) if options['output_path'] else Path(pdf_path).parent
        
        # Se output_path è un file JSON, non generare report individuali
        if options.get('output_json_only', False):
            # Non generare report individuali quando si usa -o report.json
            options['save_full'] = False
            options['save_simple'] = False
            options['save_report'] = False
        
        # Se output_path è un file (termina con .json), usa la sua directory come output_dir
        if output_path and str(output_path).lower().endswith('.json'):
            output_dir = output_path.parent
        else:
            output_dir = output_path
            
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_name = Path(pdf_path).stem

        # Show conversion message only if saving JSON outputs and not in quiet mode
        if (options['save_full'] or options['save_simple']) and not options['quiet']:
            print("🔄 Converting PDF to JSON structure...", file=sys.stderr)
        
        # Convert PDF to JSON
        pdf_json = pdf_to_json(pdf_path_to_analyze)
        
        # Extract and simplify content
        if 'StructTreeRoot' not in pdf_json:
            if not options['quiet']:
                print("⚠️  Warning: No structure tree found in PDF", file=sys.stderr)
            results = []
        else:
            results = extract_content(pdf_json['StructTreeRoot'])
        
        # Create simplified JSON
        simplified_json = create_simplified_json(pdf_json, results)
        
        # Save metadata for the result
        result["metadata"] = simplified_json.get("metadata", {})
        
        # Save full JSON if requested
        if options['save_full']:
            full_path = output_dir / f"{pdf_name}_full.json"
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(pdf_json, f, indent=2, ensure_ascii=False)
            if not options['quiet']:
                print(f"💾 Full JSON saved to: {full_path}")

        # Save simplified JSON if requested
        if options['save_simple']:
            simplified_path = output_dir / f"{pdf_name}_simplified.json"
            with open(simplified_path, 'w', encoding='utf-8') as f:
                json.dump(simplified_json, f, indent=2, ensure_ascii=False)
            if not options['quiet']:
                print(f"💾 Simplified JSON saved to: {simplified_path}")

        # Show document structure if requested and not in multi-file mode
        if options['show_structure'] and not options.get('multi_file_mode', False):
            # Use Rich formatter if requested and available
            use_rich = options.get('use_rich', False)
            
            if use_rich and RICH_AVAILABLE:
                # Use Rich for display - choose between tree or panel mode
                if options.get('use_tree', False):
                    display_document_structure_tree(simplified_json.get('content', []))
                else:
                    display_document_structure(simplified_json.get('content', []))
            else:
                # If Rich is not available or not selected, use the default formatter
                if use_rich and not RICH_AVAILABLE:
                    print("\n⚠️  Rich library not available, using default formatting.", file=sys.stderr)
                
                print("\n📄 Document Structure:")
                print("Note: Colors are used to highlight different tag types and do not indicate errors:")
                print(f"  {COLOR_GREEN}[P]{COLOR_RESET}: Paragraphs")
                print(f"  {COLOR_RED}[H1-H6]{COLOR_RESET}: Headings")
                print(f"  {COLOR_ORANGE}[Figure]{COLOR_RESET}: Images")
                print(f"  {COLOR_PURPLE}[Table]{COLOR_RESET}: Tables")
                print(f"  {COLOR_BLUE}[List]{COLOR_RESET}: Lists")
                print("-" * 40)
                for element in simplified_json.get('content', []):
                    print_formatted_content(element)
                print("-" * 40)

        # Run validation
        validator = AccessibilityValidator()
        validator.validate_metadata(simplified_json.get('metadata', {}))
        validator.validate_empty_elements(simplified_json.get('content', []))
        validator.validate_figures(simplified_json.get('content', []))
        validator.validate_heading_structure(simplified_json.get('content', []))
        validator.validate_tables(simplified_json.get('content', []))
        validator.validate_possible_unordered_lists(simplified_json.get('content', []))
        validator.validate_possible_ordered_lists(simplified_json.get('content', []))
        validator.validate_misused_unordered_lists(simplified_json.get('content', []))
        validator.validate_consecutive_lists(simplified_json.get('content', []))
        validator.validate_excessive_underscores(simplified_json.get('content', []))
        validator.validate_spaced_capitals(simplified_json.get('content', []))
        validator.validate_extra_spaces(simplified_json.get('content', []))
        validator.validate_links(simplified_json.get('content', []))
        validator.validate_italian_accents(simplified_json.get('content', []))
        
        # Store validation results
        result["issues"] = validator.issues.copy()
        result["warnings"] = validator.warnings.copy()
        result["score"] = validator.calculate_weighted_score()
        
        # Show validation results if requested and not in multi-file mode
        if options['show_validation'] and not options.get('multi_file_mode', False):
            validator.print_console_report()
        
        # Save validation report if requested
        if options['save_report']:
            report_json = validator.generate_json_report()
            
            # Add a separate section for accent issues in the JSON report
            accent_warnings = [w for w in validator.warnings if "accent" in w.lower() or "apostrophe" in w.lower()]
            if accent_warnings:
                report_json["validation_results"]["accent_issues"] = accent_warnings
            
            report_path = output_dir / f"{pdf_name}_validation_report.json"
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report_json, f, indent=2)
            if not options['quiet']:
                print(f"\n💾 Validation report saved to: {report_path}")
        
        if not options['quiet'] and not options.get('multi_file_mode', False):
            print("\n✨ Analysis complete!")
            
    except Exception as e:
        result["error"] = str(e)
        if not options.get('multi_file_mode', False):
            print(f"❌ Error: {str(e)}", file=sys.stderr)
    finally:
        # Clean up temporary file if needed
        if cleanup_needed and tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except:
                pass
    
    return result

def analyze_multiple_pdfs(pdf_paths: List[str], options: dict, max_workers: Optional[int] = None) -> None:
    """
    Analyze multiple PDF files, potentially in parallel.
    
    Args:
        pdf_paths: List of PDF file paths to analyze
        options: Analysis options
        max_workers: Maximum number of worker processes (None = auto-detect)
    """
    if not pdf_paths:
        print("❌ Error: No PDF files found to analyze", file=sys.stderr)
        sys.exit(1)
    
    # Se c'è un solo file, usiamo il flusso standard di elaborazione
    if len(pdf_paths) == 1 and not options.get('output_json_only', False):
        try:
            # Per un singolo file non usiamo la modalità multi-file
            # così l'output sarà completo
            analyze_pdf(pdf_paths[0], options)
        except Exception as e:
            print(f"❌ Error processing {pdf_paths[0]}: {str(e)}", file=sys.stderr)
            sys.exit(1)
        return
    
    # Da qui in poi è per più file o per output JSON unico
    # Mark this as multi-file mode for all files
    multi_options = options.copy()
    multi_options['multi_file_mode'] = True
    
    # Set default max workers based on CPU count
    if max_workers is None:
        max_workers = max(1, cpu_count() - 1)  # Leave one CPU free for system tasks
    
    # Prepare results collection
    all_results = []
    total_files = len(pdf_paths)
    processed = 0
    
    print(f"🚀 Analyzing {total_files} PDF files using {max_workers} workers...")
    
    # Use parallel processing for multiple files
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all files for processing
        future_to_path = {executor.submit(analyze_pdf, path, multi_options): path for path in pdf_paths}
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_path):
            processed += 1
            pdf_path = future_to_path[future]
            
            try:
                result = future.result()
                all_results.append(result)
                
                # Print simplified result
                print_file_result(result, processed, total_files)
                
            except Exception as e:
                print(f"\r❌ Error processing {pdf_path}: {str(e)}" + " " * 20, file=sys.stderr)
                all_results.append({
                    "file": pdf_path,
                    "error": str(e),
                    "issues": [],
                    "warnings": []
                })
    
    # Print summary only if not generating a single JSON file silently
    if not options.get('quiet', False):
        print_summary(all_results)
    
    # Save multi-file report if requested or if output_path is a JSON file
    # Questa è la condizione corretta che garantisce che venga creato un report JSON
    if options.get('output_json_only', False) or options.get('save_report', False):
        save_multi_report(all_results, options.get('output_path'))

def print_file_result(result: Dict, current: int, total: int) -> None:
    """Print simplified result for a single file in multi-file mode"""
    file_name = os.path.basename(result["file"])
    issues_count = len(result.get("issues", []))
    warnings_count = len(result.get("warnings", []))
    
    # Determine emoji based on issues count
    if "error" in result:
        emoji = "❌"
    elif issues_count == 0 and warnings_count == 0:
        emoji = "✅"
    elif issues_count == 0:
        emoji = "⚠️"
    else:
        emoji = "❗"
    
    # Format the output
    progress = f"[{current}/{total}]"
    score_text = f"Score: {result.get('score', 0):.1f}%" if "score" in result else "N/A"
    issues_text = f"Issues: {issues_count}"
    warnings_text = f"Warnings: {warnings_count}"
    
    # Print with carriage return for nice progress display
    print(f"\r{progress} {emoji} {file_name:<40} {score_text:<15} {issues_text:<15} {warnings_text}", flush=True)

def print_summary(results: List[Dict]) -> None:
    """Print summary of all analyzed files"""
    total_files = len(results)
    files_with_errors = sum(1 for r in results if "error" in r)
    files_with_issues = sum(1 for r in results if len(r.get("issues", [])) > 0)
    files_with_warnings = sum(1 for r in results if len(r.get("warnings", [])) > 0)
    
    total_issues = sum(len(r.get("issues", [])) for r in results)
    total_warnings = sum(len(r.get("warnings", [])) for r in results)
    
    # Calculate average score excluding errors
    valid_scores = [r.get("score", 0) for r in results if "score" in r]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
    
    print("\n" + "=" * 80)
    print("📊 RIEPILOGO ANALISI MULTIPLA")
    print("=" * 80)
    print(f"📁 File analizzati: {total_files}")
    print(f"✅ File senza problemi: {total_files - files_with_errors - files_with_issues - files_with_warnings}")
    print(f"❌ File con errori di elaborazione: {files_with_errors}")
    print(f"❗ File con problemi di accessibilità: {files_with_issues}")
    print(f"⚠️ File con warning: {files_with_warnings}")
    print(f"📝 Totale problemi: {total_issues}")
    print(f"📝 Totale warning: {total_warnings}")
    print(f"🏆 Punteggio medio di accessibilità: {avg_score:.1f}%")
    print("=" * 80)

def save_multi_report(results: List[Dict], output_path: Optional[str] = None) -> None:
    """
    Save a consolidated JSON report for multiple files
    
    Args:
        results: List of analysis results
        output_path: Path where to save the report (can be a directory or a .json file)
    """
    if not results:
        return
    
    # Define the report path
    if output_path and output_path.lower().endswith('.json'):
        # Use the exact path provided
        report_path = Path(output_path)
        # Create parent directory if needed
        report_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        # Use a directory with a timestamped filename
        if output_path:
            out_dir = Path(output_path)
        else:
            # Use current directory if no output path specified
            out_dir = Path.cwd()
        
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Create timestamped filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = out_dir / f"multi_report_{timestamp}.json"
    
    # Create multi-file report structure with key information
    report = {
        "report_type": "multi_file_analysis",
        "timestamp": datetime.datetime.now().isoformat(),
        "total_files": len(results),
        "summary": {
            "files_analyzed": len(results),
            "files_with_errors": sum(1 for r in results if "error" in r),
            "files_with_issues": sum(1 for r in results if len(r.get("issues", [])) > 0),
            "files_with_warnings": sum(1 for r in results if len(r.get("warnings", [])) > 0),
            "total_issues": sum(len(r.get("issues", [])) for r in results),
            "total_warnings": sum(len(r.get("warnings", [])) for r in results),
            "average_accessibility_score": sum(r.get("score", 0) for r in results if "score" in r) / 
                                         sum(1 for r in results if "score" in r) if any("score" in r for r in results) else 0
        },
        "files": []
    }
    
    # Add each file's results in a clear format
    for result in results:
        file_entry = {
            "file_name": os.path.basename(result["file"]),
            "file_path": result["file"],
            "accessibility_score": result.get("score", 0),
            "issues_count": len(result.get("issues", [])),
            "warnings_count": len(result.get("warnings", [])),
            "metadata": result.get("metadata", {})
        }
        
        # Add detailed issues and warnings if available
        if "issues" in result:
            file_entry["issues"] = result["issues"]
        if "warnings" in result:
            file_entry["warnings"] = result["warnings"]
        if "error" in result:
            file_entry["error"] = result["error"]
            file_entry["has_error"] = True
        else:
            file_entry["has_error"] = False
            
        report["files"].append(file_entry)
    
    # Calculate stats for accessibility rating categories
    score_categories = {
        "excellent": sum(1 for r in results if r.get("score", 0) >= 90 and "error" not in r),
        "good": sum(1 for r in results if 70 <= r.get("score", 0) < 90 and "error" not in r),
        "fair": sum(1 for r in results if 50 <= r.get("score", 0) < 70 and "error" not in r),
        "poor": sum(1 for r in results if r.get("score", 0) < 50 and "error" not in r)
    }
    report["summary"]["score_categories"] = score_categories
    
    # Save the report
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Report salvato in: {report_path}")

def main():
    try:
        parser = argparse.ArgumentParser(
            description='PDF Analysis Tool: Convert to JSON and validate accessibility',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  Basic usage (shows full analysis by default)
  avalpdf document.pdf
  
  Analyze remote PDF via URL (use quotes for URLs with special characters)
  avalpdf "https://example.com/document.pdf?param=value"
  
  Save reports to specific directory
  avalpdf document.pdf -o /path/to/output --report --simple
  
  Save all files without console output
  avalpdf document.pdf --full --simple --report --quiet
  
  Use Rich formatting for structure display
  avalpdf document.pdf --rich
  
  Multiple file analysis
  avalpdf file1.pdf file2.pdf file3.pdf
  
  Using wildcard pattern (use quotes in some shells)
  avalpdf "*.pdf"
  
  Process all PDFs in a directory
  avalpdf /path/to/directory/
  
  Save multi-file report to specific JSON file
  avalpdf pdfs/bugs/open/*.pdf -o report.json
"""
        )
        
        parser.add_argument('inputs', nargs='+', help='Input PDF files, URLs, directories, or wildcard patterns (e.g., *.pdf)')
        parser.add_argument('--output-path', '-o', help='Output path: directory for individual reports or .json file for consolidated report')
        parser.add_argument('--full', action='store_true', help='Save full JSON output')
        parser.add_argument('--simple', action='store_true', help='Save simplified JSON output')
        parser.add_argument('--report', action='store_true', help='Save validation report')
        parser.add_argument('--show-structure', action='store_true', help='Show document structure in console')
        parser.add_argument('--show-validation', action='store_true', help='Show validation results in console')
        parser.add_argument('--quiet', '-q', action='store_true', help='Suppress all console output except errors')
        parser.add_argument('--rich', action='store_true', help='Use Rich library for enhanced document structure display')
        parser.add_argument('--tree', action='store_true', help='Use tree view instead of panel view with Rich')
        parser.add_argument('--workers', '-w', type=int, help='Maximum number of parallel workers (default: auto)')
        parser.add_argument('--version', '-v', action='version', version=f'avalpdf {__version__}', help='Show program version and exit')
        
        # Parse arguments
        args = parser.parse_args()
        
        # Expand wildcards and directory references to get list of PDF files
        expanded_inputs = expand_file_paths(args.inputs)
        
        # If no display options specified, enable both structure and validation display
        show_structure = args.show_structure
        show_validation = args.show_validation
        if not any([args.show_structure, args.show_validation, args.quiet]):
            show_structure = True
            show_validation = True
        
        # Prepare options dictionary
        options = {
            'output_path': args.output_path,
            'save_full': args.full,
            'save_simple': args.simple,
            'save_report': args.report,
            'show_structure': show_structure,
            'show_validation': show_validation,
            'quiet': args.quiet,
            'use_rich': args.rich,
            'use_tree': args.tree
        }
        
        # Configurazione speciale per output JSON
        if options['output_path'] and options['output_path'].lower().endswith('.json'):
            options['output_json_only'] = True
            # Quando si specifica un file JSON di output, disabilita gli altri output a meno che
            # non siano esplicitamente richiesti dall'utente
            if not args.full:
                options['save_full'] = False
            if not args.simple:
                options['save_simple'] = False
            if not args.report:
                options['save_report'] = False
        
        # Process the files
        analyze_multiple_pdfs(expanded_inputs, options, args.workers)
        
    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

