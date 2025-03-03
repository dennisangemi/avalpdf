#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import sys
from pdfixsdk import *
import ctypes
from typing import Dict, List, Tuple
import tempfile
import urllib.request
import urllib.parse

from avalpdf.converter import pdf_to_json
from avalpdf.extractor import extract_content, create_simplified_json
from avalpdf.formatter import print_formatted_content, COLOR_GREEN, COLOR_RED, COLOR_ORANGE, COLOR_PURPLE, COLOR_BLUE, COLOR_RESET
from avalpdf.utils import download_pdf, is_url
from avalpdf.validator import AccessibilityValidator



def analyze_pdf(pdf_path: str, options: dict) -> None:
    """
    Analyze a PDF file with configurable outputs
    """
    try:
        # Setup output directory
        output_dir = Path(options['output_dir']) if options['output_dir'] else Path(pdf_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_name = Path(pdf_path).stem

        # Show conversion message only if saving JSON outputs
        if (options['save_full'] or options['save_simple']) and not options['quiet']:
            print("🔄 Converting PDF to JSON structure...", file=sys.stderr)
        
        # Convert PDF to JSON
        pdf_json = pdf_to_json(pdf_path)
        
        # Extract and simplify content
        if 'StructTreeRoot' not in pdf_json:
            if not options['quiet']:
                print("⚠️  Warning: No structure tree found in PDF", file=sys.stderr)
            results = []
        else:
            results = extract_content(pdf_json['StructTreeRoot'])
        
        # Create simplified JSON
        simplified_json = create_simplified_json(pdf_json, results)
        
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

        # Show document structure if requested
        if options['show_structure']:
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

        # Run validation if requested
        if options['save_report'] or options['show_validation']:
            if not options['quiet']:
                print("\n🔍 Running accessibility validation...")
            
            validator = AccessibilityValidator()
            validator.validate_metadata(simplified_json.get('metadata', {}))
            validator.validate_empty_elements(simplified_json.get('content', []))
            validator.validate_figures(simplified_json.get('content', []))
            validator.validate_heading_structure(simplified_json.get('content', []))
            validator.validate_tables(simplified_json.get('content', []))  # Add table validation
            validator.validate_possible_unordered_lists(simplified_json.get('content', []))  # Add this
            validator.validate_possible_ordered_lists(simplified_json.get('content', []))    # Add this
            validator.validate_misused_unordered_lists(simplified_json.get('content', []))  # Add this
            validator.validate_consecutive_lists(simplified_json.get('content', []))  # Aggiunta questa riga
            validator.validate_excessive_underscores(simplified_json.get('content', []))
            validator.validate_spaced_capitals(simplified_json.get('content', []))
            validator.validate_extra_spaces(simplified_json.get('content', []))
            validator.validate_links(simplified_json.get('content', []))  # Add link validation
            
            # Show validation results if requested
            if options['show_validation']:
                validator.print_console_report()
            
            # Save validation report if requested
            if options['save_report']:
                report_path = output_dir / f"{pdf_name}_validation_report.json"
                with open(report_path, 'w', encoding='utf-8') as f:
                    json.dump(validator.generate_json_report(), f, indent=2)
                if not options['quiet']:
                    print(f"\n💾 Validation report saved to: {report_path}")
        
        if not options['quiet']:
            print("\n✨ Analysis complete!")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

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
"""
        )
        
        parser.add_argument('input', help='Input PDF file or URL (use quotes for URLs with special characters)')
        parser.add_argument('--output-dir', '-o', help='Output directory for JSON files')
        parser.add_argument('--full', action='store_true', help='Save full JSON output')
        parser.add_argument('--simple', action='store_true', help='Save simplified JSON output')
        parser.add_argument('--report', action='store_true', help='Save validation report')
        parser.add_argument('--show-structure', action='store_true', help='Show document structure in console')
        parser.add_argument('--show-validation', action='store_true', help='Show validation results in console')
        parser.add_argument('--quiet', '-q', action='store_true', help='Suppress all console output except errors')
        
        # Parse arguments normally, removing the special URL handling
        args = parser.parse_args()
        
        input_path = None
        cleanup_needed = False
        
        try:
            # Handle URL input
            if is_url(args.input):
                if not args.quiet:
                    print("📥 Connecting to remote source...", file=sys.stderr, flush=True)
                input_path = download_pdf(args.input)
                cleanup_needed = True
            else:
                input_path = Path(args.input)
                cleanup_needed = False

            if not input_path or not input_path.is_file():
                print(f"❌ Error: Input file '{args.input}' does not exist", file=sys.stderr)
                sys.exit(1)
            
            # If no display options specified, enable both structure and validation display
            show_structure = args.show_structure
            show_validation = args.show_validation
            if not any([args.show_structure, args.show_validation, args.quiet]):
                show_structure = True
                show_validation = True
            
            # Prepare options dictionary
            options = {
                'output_dir': args.output_dir,
                'save_full': args.full,
                'save_simple': args.simple,
                'save_report': args.report,
                'show_structure': show_structure,
                'show_validation': show_validation,
                'quiet': args.quiet
            }
            
            analyze_pdf(str(input_path), options)

        except Exception as e:
            print(f"❌ Error: {str(e)}", file=sys.stderr, flush=True)
            if cleanup_needed and input_path and input_path.exists():
                try:
                    input_path.unlink()
                except:
                    pass
            sys.exit(1)
        finally:
            if cleanup_needed and input_path and input_path.exists():
                try:
                    input_path.unlink()
                except:
                    pass
            sys.exit(0)

    except KeyboardInterrupt:
        print("\n⚠️ Operation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

