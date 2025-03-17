from typing import Dict, List, Tuple
import re
from avalpdf.formatter import is_element_empty

class AccessibilityValidator:
    def __init__(self):
        self.issues = []
        self.warnings = []
        self.successes = []
        self.is_tagged = False
        
        self.check_weights = {
            'tagging': 35,          # Aumentato perché fondamentale
            'title': 20,           # Aumentato perché molto importante
            'language': 20,        # Aumentato perché molto importante
            'headings': 5,         # Ridotto perché un titolo vuoto è meno grave
            'alt_text': 4,         # Invariato
            'figures': 4,          # Invariato
            'tables': 4,           # Invariato
            'lists': 4,            # Invariato
            'consecutive_lists': 2,    # Nuovo peso per il check delle liste consecutive
            'empty_elements': 1,   # Ridotto al minimo perché meno importante
            'underlining': 1,      # Invariato
            'spacing': 1,          # Invariato
            'italian_accents': 2,  # Nuovo peso per controllo accenti italiani
            'extra_spaces': 0.5,   # Ridotto perché poco rilevante
            'links': 0.5          # Ridotto perché poco rilevante
        }
        self.check_scores = {k: 0 for k in self.check_weights}
        self.empty_elements_count = {
            'paragraphs': 0,
            'table_cells': 0,
            'headings': 0,
            'spans': 0,
            'total': 0
        }

    def validate_metadata(self, metadata: Dict) -> None:
        # Check tagged status first
        tagged = metadata.get('tagged')
        if not tagged or tagged.lower() != 'true':
            self.issues.append("Document is not tagged")
            self.check_scores['tagging'] = 0
            self.is_tagged = False
        else:
            self.successes.append("Document is tagged")
            self.check_scores['tagging'] = 100
            self.is_tagged = True
            
        # Check title with clearer message
        if not metadata.get('title'):
            self.issues.append("Document metadata is missing title property")
            self.check_scores['title'] = 0
        else:
            self.successes.append("Document metadata includes title property")
            self.check_scores['title'] = 100
            
        # Check language
        lang = metadata.get('lang', '').lower()
        if not lang.startswith('it'):
            self.issues.append(f"Document language is not Italian (found: {lang})")
            self.check_scores['language'] = 0
        else:
            self.successes.append("Document language is Italian")
            self.check_scores['language'] = 100

    def validate_empty_elements(self, content: List) -> None:
        """Check for any empty elements in the document"""
        if not self.is_tagged:
            self.check_scores['empty_elements'] = 0
            return
            
        def check_element(element: Dict, path: str = "") -> None:
            tag = element.get('tag', '')
            text = element.get('text', '')
            children = element.get('children', [])
            
            current_path = f"{path}/{tag}" if path else tag
            
            # Check for empty content
            has_no_content = not text.strip() and not children
            if has_no_content:
                if tag == 'P':
                    self.empty_elements_count['paragraphs'] += 1
                    self.empty_elements_count['total'] += 1
                elif tag.startswith('H'):
                    self.empty_elements_count['headings'] += 1
                    self.empty_elements_count['total'] += 1
                elif tag == 'Span':
                    self.empty_elements_count['spans'] += 1
                    self.empty_elements_count['total'] += 1
                    
            # Special check for table cells with deeply nested content
            if tag == 'Table':
                table_content = element.get('content', {})
                
                # Helper function to check if a cell is truly empty
                def is_cell_truly_empty(cell):
                    # Not a dictionary
                    if not isinstance(cell, dict):
                        return True
                        
                    # Cell has direct text content
                    if cell.get('text', '').strip():
                        return False
                        
                    # Cell has no children
                    if not cell.get('children'):
                        return True
                        
                    # Check each child deeply for content
                    for child in cell.get('children', []):
                        # If the child is a nested TD/TH
                        if isinstance(child, dict) and child.get('tag') in ['TD', 'TH']:
                            if not is_cell_truly_empty(child):
                                return False
                        # If the child is any other tag (like P, Span, etc.)
                        elif isinstance(child, dict):
                            # Check if child has direct text
                            if child.get('text', '').strip():
                                return False
                            # Check grandchildren recursively
                            for grandchild in child.get('children', []):
                                if isinstance(grandchild, dict) and (
                                   grandchild.get('text', '').strip() or
                                   grandchild.get('tag') == 'Figure' or
                                   not is_cell_truly_empty(grandchild)):
                                    return False
                            
                    # If we get here, the cell is truly empty
                    return True
                
                # Check table headers
                for row in table_content.get('headers', []):
                    for cell in row:
                        if is_cell_truly_empty(cell):
                            self.empty_elements_count['table_cells'] += 1
                            self.empty_elements_count['total'] += 1
                
                # Check table data rows
                for row in table_content.get('rows', []):
                    for cell in row:
                        if is_cell_truly_empty(cell):
                            self.empty_elements_count['table_cells'] += 1
                            self.empty_elements_count['total'] += 1
            
            # Check children recursively
            for child in element.get('children', []):
                check_element(child, current_path)
                
        # Reset counters
        self.empty_elements_count = {k: 0 for k in self.empty_elements_count}
        
        # Check all elements
        for element in content:
            check_element(element)
            
        # ... rest of existing validate_empty_elements code ...

    def is_complex_alt_text(self, alt_text: str) -> tuple[bool, str]:
        """
        Verifica se l'alt text contiene pattern problematici
        Returns: (is_complex, reason)
        """
        import re
        
        # Verifica estensioni di file comuni
        file_ext_pattern = r'\.(png|jpe?g|gif|bmp|tiff?|pdf|docx?|xlsx?|pptx?)$'
        if re.search(file_ext_pattern, alt_text, re.IGNORECASE):
            return True, "contains file extension"

        # Verifica nomi file che contengono trattini, underscore o numeri
        complex_name_pattern = r'[-_][a-zA-Z0-9]+[-_0-9]*\.'
        if re.search(complex_name_pattern, alt_text):
            return True, "contains complex filename"
            
        # Verifica se contiene "File:" o "Image:" all'inizio
        if alt_text.startswith(("File:", "Image:")):
            return True, "starts with 'File:' or 'Image:'"

        return False, ""

    def validate_figures(self, content: List) -> None:
        """Validate figures and their alt text - checks recursively through all structures"""
        if not self.is_tagged:
            self.check_scores['figures'] = 0
            self.check_scores['alt_text'] = 0
            return
            
        figures = []
        figures_without_alt = []
        figures_with_complex_alt = []
        
        def check_figures_recursive(element: Dict, path: str = "", page_num: int = 1) -> None:
            # Check cambio pagina
            if 'Pg' in element:
                page_num = int(element['Pg'])
                
            # Process current element
            tag = element.get('tag', '')
            current_path = f"{path}/{tag}" if path else tag
            
            if tag == 'Figure':
                figure_num = len(figures) + 1
                figures.append((current_path, figure_num, page_num))
                alt_text = element.get('text', '').strip()
                if not alt_text:
                    figures_without_alt.append((current_path, figure_num, page_num))
                else:
                    is_complex, reason = self.is_complex_alt_text(alt_text)
                    if is_complex:
                        figures_with_complex_alt.append((current_path, alt_text, reason, figure_num, page_num))
            
            # Check children
            children = element.get('children', [])
            if children:
                for child in children:
                    check_figures_recursive(child, current_path, page_num)
                    
            # Special handling for table cells and other structured content
            if tag == 'Table':
                table_content = element.get('content', {})
                # Check headers
                for row in table_content.get('headers', []):
                    for cell in row:
                        check_figures_recursive(cell, f"{current_path}/header", page_num)
                # Check rows
                for row in table_content.get('rows', []):
                    for cell in row:
                        check_figures_recursive(cell, f"{current_path}/row", page_num)
        
        # Start recursive check
        for element in content:
            check_figures_recursive(element)
        
        # Update validation results
        if figures:
            if figures_without_alt:
                missing_figures = [f"Figure {num} (page {page})" for _, num, page in figures_without_alt]
                self.issues.append(f"Found {len(figures_without_alt)} figures without alt text: {', '.join(missing_figures)}")
                self.check_scores['figures'] = 50
            else:
                count = len(figures)
                self.successes.append(f"Found {count} figure{'' if count == 1 else 's'} with alternative text")
                self.check_scores['figures'] = 100

            if figures_with_complex_alt:
                for _, alt_text, reason, num, page in figures_with_complex_alt:
                    self.warnings.append(f"Figure {num} (page {page}) has problematic alt text ({reason}): '{alt_text}'")
                self.check_scores['alt_text'] = 50
            else:
                self.check_scores['alt_text'] = 100
        else:
            self.check_scores['figures'] = 0
            self.check_scores['alt_text'] = 0

    def validate_heading_structure(self, content: List) -> None:
        if not self.is_tagged:
            self.check_scores['headings'] = 0
            return
            
        # Track headings with their location and level
        headings = []  # Will store tuples of (level, path)
        empty_headings = []  # Will store tuples of (level, path)
        headings_with_only_figures = []  # Will store tuples of (level, path)
        
        # Track the order of headings in the document to determine the first one
        ordered_headings = []  # Will store tuples of (level, path, is_empty, has_only_figures)
        
        def collect_headings(element: Dict, path: str = "") -> None:
            """Recursively collect all headings in the document, including nested ones"""
            tag = element.get('tag', '')
            current_path = f"{path}/{tag}" if path else tag
            
            # Check if this element is a heading
            if tag.startswith('H'):
                try:
                    level = int(tag[1:])
                    # Check if the heading contains only figures and no text
                    has_only_figure = False
                    has_text = False
                    
                    # Check direct text content
                    if element.get('text', '').strip():
                        has_text = True
                    
                    # Check children for figures and text
                    children = element.get('children', [])
                    if children:
                        # Check if the only child is a Figure
                        if len(children) == 1 and children[0].get('tag') == 'Figure':
                            has_only_figure = True
                        # Or if all children are either empty or figures
                        elif all(child.get('tag') == 'Figure' or 
                                 is_element_empty(child) for child in children):
                            has_only_figure = True and any(child.get('tag') == 'Figure' for child in children)
                        
                        # If any child has text, mark as having text
                        for child in children:
                            if child.get('text', '').strip():
                                has_text = True
                                break
                            # Check deeper for text
                            for grandchild in child.get('children', []):
                                if isinstance(grandchild, dict) and grandchild.get('text', '').strip():
                                    has_text = True
                                    break
                    
                    # Store in ordered list for determining first heading
                    is_empty = is_element_empty(element)
                    ordered_headings.append((level, current_path, is_empty, has_only_figure and not has_text))
                    
                    # Decide how to classify this heading
                    if has_only_figure and not has_text:
                        headings_with_only_figures.append((level, current_path))
                    elif is_empty:
                        empty_headings.append((level, current_path))
                    else:
                        headings.append((level, current_path))
                except ValueError:
                    pass
            
            # Check children recursively
            for child in element.get('children', []):
                collect_headings(child, current_path)
                
            # Special handling for tables to find headings inside cells
            if tag == 'Table':
                table_content = element.get('content', {})
                
                # Process header cells
                for i, row in enumerate(table_content.get('headers', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            cell_path = f"{current_path}/header[{i}][{j}]"
                            process_cell_for_headings(cell, cell_path)
                
                # Process data cells
                for i, row in enumerate(table_content.get('rows', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            cell_path = f"{current_path}/row[{i}][{j}]"
                            process_cell_for_headings(cell, cell_path)
                            
        def process_cell_for_headings(cell: Dict, cell_path: str) -> None:
            """Process a table cell to find any headings inside it"""
            # Check for direct headings in the cell
            cell_tag = cell.get('tag', '')
            if cell_tag.startswith('H'):
                try:
                    level = int(cell_tag[1:])
                    # Check if cell has only figure and no text
                    has_only_figure = False
                    has_text = cell.get('text', '').strip() != ''
                    
                    # Check for figures in children
                    children = cell.get('children', [])
                    if children and not has_text:
                        if len(children) == 1 and children[0].get('tag') == 'Figure':
                            has_only_figure = True
                    
                    if has_only_figure:
                        headings_with_only_figures.append((level, cell_path))
                    elif is_element_empty(cell):
                        empty_headings.append((level, cell_path))
                    else:
                        headings.append((level, cell_path))
                except ValueError:
                    pass
                    
            # Check for headings in cell children
            for child in cell.get('children', []):
                child_tag = child.get('tag', '')
                child_path = f"{cell_path}/{child_tag}"
                
                if child_tag.startswith('H'):
                    try:
                        level = int(child_tag[1:])
                        # Check if heading has only figure
                        has_only_figure = False
                        has_text = child.get('text', '').strip() != ''
                        
                        # Check children for figures
                        grandchildren = child.get('children', [])
                        if grandchildren and not has_text:
                            if len(grandchildren) == 1 and grandchildren[0].get('tag') == 'Figure':
                                has_only_figure = True
                        
                        if has_only_figure:
                            headings_with_only_figures.append((level, child_path))
                        elif is_element_empty(child):
                            empty_headings.append((level, child_path))
                        else:
                            headings.append((level, child_path))
                    except ValueError:
                        pass
                        
                # Recursively process nested elements
                if child.get('children'):
                    process_cell_for_headings(child, child_path)
        
        # Start the heading collection
        for element in content:
            collect_headings(element)
        
        # Get just the levels for simpler checks
        heading_levels = [level for level, _ in headings]
        empty_levels = [level for level, _ in empty_headings]
        figure_only_levels = [level for level, _ in headings_with_only_figures]
        
        # Check for the first heading - must be H1
        if ordered_headings:
            first_heading = ordered_headings[0]
            first_level = first_heading[0]
            if first_level != 1:
                # First heading is not H1 - this is an error
                self.issues.append(f"First heading in document is H{first_level}, but should be H1 - improper heading hierarchy")
                self.check_scores['headings'] = max(self.check_scores['headings'], 30)
        
        # Get only h1s with figures for specific error reporting
        h1_figure_only_paths = [path for level, path in headings_with_only_figures if level == 1]
        
        # Check each H1 with only images individually and report them once
        if h1_figure_only_paths:
            # Multiple H1s with only images
            if len(h1_figure_only_paths) > 1:
                self.issues.append(f"Found {len(h1_figure_only_paths)} H1 headings that contain only images and no text - this is not accessible")
            else:
                # Single H1 with only images
                self.issues.append("Found an H1 heading that contains only images and no text - this is not accessible")
                
            # Set a lower headings score when we have image-only H1s
            self.check_scores['headings'] = max(self.check_scores['headings'], 30)
        
        # Scoring logic based on collected headings
        if not heading_levels and not figure_only_levels and empty_headings:
            # Only empty headings found - this is a real issue
            unique_empty_levels = sorted(set(empty_levels))
            self.issues.append(f"Found {len(empty_headings)} empty heading{'s' if len(empty_headings) > 1 else ''} " +
                              f"(H{', H'.join(map(str, unique_empty_levels))}) and no valid headings")
            self.check_scores['headings'] = 0
            return
        
        if empty_headings:
            # Find levels that have both valid and empty headings
            valid_level_set = set(heading_levels)
            empty_level_set = set(empty_levels)
            
            # Report empty headings that don't have any valid heading of the same level as issues
            levels_with_only_empty = empty_level_set - valid_level_set
            if levels_with_only_empty:
                # Only report as issues levels that have no valid headings
                levels_str = ", ".join(f"H{level}" for level in sorted(levels_with_only_empty))
                count = sum(1 for level in empty_levels if level in levels_with_only_empty)
                self.issues.append(f"Found {count} empty heading{'s' if count > 1 else ''} with no valid counterparts ({levels_str})")
            
            # Report empty headings that have at least one valid heading of the same level as warnings
            levels_with_both = empty_level_set.intersection(valid_level_set)
            if levels_with_both:
                # Report as warnings since there are valid headings
                levels_str = ", ".join(f"H{level}" for level in sorted(levels_with_both))
                count = sum(1 for level in empty_levels if level in levels_with_both)
                self.warnings.append(f"Found {count} empty heading{'s' if count > 1 else ''} ({levels_str}) alongside valid headings of the same level")
            
            # Set score based on the situation
            if levels_with_only_empty:
                self.check_scores['headings'] = 30  # More severe penalty
            else:
                self.check_scores['headings'] = 60  # Less severe when all empty headings have valid counterparts
        
        if not heading_levels and not figure_only_levels and not empty_headings:
            # No headings at all
            self.issues.append("Document has no headings - every document should have at least an H1 heading")
            self.check_scores['headings'] = 0
            return
        
        if heading_levels or figure_only_levels:  # Validate structure for non-empty headings and figure-only headings
            # Check for at least one valid H1 anywhere in the document
            if 1 not in heading_levels:
                # If we have only H1s with figures but no text H1s
                if 1 in figure_only_levels:
                    self.issues.append("Document has H1 heading with only images, no text - this is not accessible")
                else:
                    self.issues.append("Document doesn't have any H1 heading - a document should have at least one H1 heading")
                self.check_scores['headings'] = max(self.check_scores['headings'], 30)
            
            # Get all top-level headings (not inside other elements) for hierarchy analysis
            top_level_headings = []
            for level, path in headings:
                # Count only headings that are direct children of the document, not nested in tables or other elements
                path_parts = path.split('/')
                if len(path_parts) <= 3 and path_parts[0] == 'Document':  # Document/H1, Document/Sect/H1, etc.
                    top_level_headings.append((level, path))
            
            # Check if the first top-level heading is H1
            if top_level_headings and top_level_headings[0][0] > 1:
                # Only report this issue if we don't have H1s at the top level
                if not any(level == 1 for level, _ in top_level_headings):
                    self.issues.append(f"First heading at document level is H{top_level_headings[0][0]}, should be H1")
                    self.check_scores['headings'] = max(self.check_scores['headings'], 40)
            
            # Check heading hierarchy for top-level headings
            hierarchy_issues = []
            if len(top_level_headings) > 1:
                prev_level = top_level_headings[0][0]
                for level, path in top_level_headings[1:]:
                    if level > prev_level + 1:
                        hierarchy_issues.append(f"H{prev_level} followed by H{level}")
                    prev_level = level
                
                if hierarchy_issues:
                    self.issues.append("Incorrect heading hierarchy: " + ", ".join(hierarchy_issues))
                    self.check_scores['headings'] = max(self.check_scores['headings'], 50)
            
            # Final score if no issues detected
            if not any(issue for issue in self.issues if "heading" in issue.lower()):
                self.successes.append(f"Found {len(heading_levels)} heading{'s' if len(heading_levels) > 1 else ''} with correct structure")
                self.check_scores['headings'] = 100

    def validate_tables(self, content: List) -> None:
        if not self.is_tagged:
            self.check_scores['tables'] = 0
            return
            
        tables = []
        tables_without_headers = []
        empty_tables = []
        tables_with_duplicate_headers = []
        tables_with_proper_headers = []
        tables_with_multiple_header_rows = []
        tables_without_data = []
        
        # Completely rewritten function to correctly detect content in nested elements
        def is_table_completely_empty(headers, rows) -> bool:
            """Checks if a table is completely empty by recursively examining all content"""
            
            def has_content(element) -> bool:
                """Recursively check if an element or any of its children have content"""
                # Base case: not a dictionary
                if not isinstance(element, dict):
                    return isinstance(element, str) and element.strip() != ""
                    
                # Check direct text content
                if element.get('text', '').strip():
                    return True
                    
                # Figures always have content
                if element.get('tag') == 'Figure':
                    return True
                    
                # Check for headings which always have semantic value
                if element.get('tag', '').startswith('H'):
                    return True
                    
                # Lists with items have content
                if element.get('tag') == 'L' and element.get('items', []):
                    return True
                    
                # Recursively check all children
                for child in element.get('children', []):
                    if has_content(child):
                        return True
                        
                # Special case for tables
                if element.get('tag') == 'Table':
                    table_content = element.get('content', {})
                    # Check headers
                    for row in table_content.get('headers', []):
                        for cell in row:
                            if has_content(cell):
                                return True
                    # Check rows
                    for row in table_content.get('rows', []):
                        for cell in row:
                            if has_content(cell):
                                return True
                
                # No content found
                return False
            
            # Check all header cells
            for row in headers:
                for cell in row:
                    if has_content(cell):
                        return False
            
            # Check all data cells
            for row in rows:
                for cell in row:
                    if has_content(cell):
                        return False
            
            # If we get here, the table is truly empty
            return True
        
        def has_duplicate_headers(headers) -> tuple[bool, list]:
            """Checks if table headers contain duplicate non-empty text content in the same row"""
            if not headers:
                return False, []
            
            duplicates = []
            
            # Check each row for duplicates
            for row_index, row in enumerate(headers):
                row_texts = []
                row_duplicates = []
                
                for cell in row:
                    # Extract text from the cell
                    if isinstance(cell, dict):
                        text = cell.get('text', '').strip()
                        
                        # Recursively extract text from nested elements if present
                        if not text and cell.get('children'):
                            for child in cell.get('children', []):
                                if isinstance(child, dict):
                                    # Check if child is a paragraph or other text container
                                    if child.get('tag') in ['P', 'Span', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6']:
                                        child_text = child.get('text', '').strip()
                                        if child_text:
                                            text = child_text
                                            break
                    else:
                        text = str(cell).strip()
                    
                    # Only consider non-empty header text
                    if text:
                        if text in row_texts:
                            # Add meaningful information about the duplicate
                            row_duplicates.append(f"'{text}' (row {row_index+1})")
                        row_texts.append(text)
                
                # Add any duplicates found in this row
                duplicates.extend(row_duplicates)
            
            return bool(duplicates), duplicates

        def is_element_empty(element: Dict) -> bool:
            """Verifica ricorsivamente se un elemento e tutti i suoi contenuti sono vuoti"""
            if not isinstance(element, dict):
                return True
                
            # Controlla il testo diretto
            has_text = bool(element.get('text', '').strip())
            if has_text:
                return False
                
            # Controlla se è un'immagine (tag Figure)
            if element.get('tag') == 'Figure':
                return False
                
            # Controlla contenuto tabella
            if element.get('tag') == 'Table':
                table_content = element.get('content', {})
                # Controlla headers e rows
                for section in ['headers', 'rows']:
                    for row in table_content.get(section, []):
                        for cell in row:
                            if not is_element_empty(cell):
                                return False
                return True
                
            # Controlla contenuto liste
            if element.get('tag') == 'L':
                items = element.get('items', [])
                return all(not item.strip() for item in items)
                
            # Controlla ricorsivamente i figli, compresi gli Span
            children = element.get('children', [])
            if children:
                return all(is_element_empty(child) for child in children)
                
            # Se non ci sono né testo diretto né figli, l'elemento è vuoto
            return True

        def is_cell_empty(cell: Dict) -> bool:
            """Controlla se una cella è completamente vuota ricorsivamente"""
            # Handle non-dict cells (shouldn't happen but just in case)
            if not isinstance(cell, dict):
                return True
                
            # Check direct text
            cell_text = cell.get('text', '').strip()
            if cell_text:
                return False
                
            # Special case for nested TD/TH structure in the JSON
            if cell.get('tag') in ['TD', 'TH'] and 'children' in cell:
                nested_cells = [child for child in cell.get('children', []) 
                               if isinstance(child, dict) and child.get('tag') in ['TD', 'TH']]
                
                # If we have nested TD/TH, check their content
                if nested_cells:
                    for nested_cell in nested_cells:
                        if not is_cell_empty(nested_cell):
                            return False
                            
                # Also check any other children like paragraphs, figures, etc.
                other_children = [child for child in cell.get('children', [])
                                 if isinstance(child, dict) and child.get('tag') not in ['TD', 'TH']]
                                 
                for child in other_children:
                    if not is_element_empty(child):
                        return False
                        
                return True
            
            # Use the regular recursive check for all other elements
            return is_element_empty(cell)

        def count_empty_cells(table_content: Dict) -> tuple[int, List[str], List[str]]:
            """Conta le celle vuote e restituisce (count, locations, details)"""
            empty_cells = []
            empty_cells_details = []
            total_empty = 0
            
            def format_cell_content(cell):
                """Formatta i dettagli del contenuto di una cella vuota"""
                tags = []
                if isinstance(cell, dict):
                    tag = cell.get('tag', '')
                    if tag:
                        tags.append(f"{tag}")
                        if cell.get('children'):
                            for child in cell.get('children'):
                                child_tag = child.get('tag', '')
                                if child_tag:
                                    tags.append(f"{child_tag}")
                return f"[{' > '.join(tags)}]" if tags else "[empty]"
            
            # Check headers
            for i, row in enumerate(table_content.get('headers', [])):
                for j, cell in enumerate(row):
                    if is_cell_empty(cell):
                        total_empty += 1
                        location = f"header[{i}][{j}]"
                        empty_cells.append(location)
                        empty_cells_details.append(f"{location} {format_cell_content(cell)}")
            
            # Check data rows - Fix the iteration over row cells
            for i, row in enumerate(table_content.get('rows', [])):
                for j, cell in enumerate(row):  # Fixed: removed the tuple unpacking that was causing the error
                    if is_cell_empty(cell):
                        total_empty += 1
                        location = f"row[{i}][{j}]"
                        empty_cells.append(location)
                        empty_cells_details.append(f"{location} {format_cell_content(cell)}")
            
            return total_empty, empty_cells, empty_cells_details

        def check_tables(element: Dict, path: str = "") -> None:
            tag = element.get('tag', '')
            
            if tag == 'Table':
                table_num = len(tables) + 1
                table_content = element.get('content', {})
                headers = table_content.get('headers', [])
                rows = table_content.get('rows', [])
                
                # Verifica se ci sono intestazioni di riga (celle con isHeader o isRowHeader = True)
                has_row_headers = any(
                    any(isinstance(cell, dict) and (cell.get('isHeader', False) or cell.get('isRowHeader', False)) 
                        for cell in row)
                    for row in rows
                )
                
                # First check if table is structurally empty
                if not headers and not rows:
                    empty_tables.append(f"Table {table_num}")
                    return
                # Then check if table has structure but all cells are empty
                elif is_table_completely_empty(headers, rows):
                    empty_tables.append(f"Table {table_num}")
                else:
                    tables.append(f"Table {table_num}")
                    
                    # Check if table has headers (ora considerando anche le intestazioni di riga)
                    if not headers and not has_row_headers:
                        tables_without_headers.append(f"Table {table_num}")
                    else:
                        # Check number of header rows
                        if len(headers) > 1:
                            tables_with_multiple_header_rows.append((f"Table {table_num}", len(headers)))
                        
                        # Check for duplicate headers
                        has_duplicates, duplicate_values = has_duplicate_headers(headers)
                        if has_duplicates:
                            tables_with_duplicate_headers.append((f"Table {table_num}", duplicate_values))
                        else:
                            tables_with_proper_headers.append(f"Table {table_num}")
                    
                    # Check if table has data rows
                    if not rows:
                        tables_without_data.append(f"Table {table_num}")
                
                # Check for empty cells with improved detection
                empty_count, empty_locations, empty_details = count_empty_cells(table_content)
                if empty_count > 0:
                    if empty_count == 1:
                        self.warnings.append(f"Table {table_num} has 1 empty cell at: {empty_details[0]}")
                    else:
                        self.warnings.append(f"Table {table_num} has {empty_count} empty cells at: {', '.join(empty_details)}")
            
            # Check children
            for child in element.get('children', []):
                check_tables(child)
        
        for element in content:
            check_tables(element)
        
        # Report issues and warnings
        if empty_tables:
            self.issues.append(f"Found empty tables: {', '.join(empty_tables)}")
        
        if tables:  # Solo se ci sono tabelle non vuote
            # Issues per tabelle senza header o senza dati
            if tables_without_headers:
                self.issues.append(f"Found tables without headers: {', '.join(tables_without_headers)}")
            if tables_without_data:
                self.issues.append(f"Found tables without data rows: {', '.join(tables_without_data)}")
            
            # Warning per tabelle con più righe di intestazione
            for table_id, num_rows in tables_with_multiple_header_rows:
                self.warnings.append(f"{table_id} has {num_rows} header rows, consider using a single header row")
            
            # Report successo per ogni tabella corretta individualmente
            for table_id in tables_with_proper_headers:
                if (not any(table_id == t[0] for t in tables_with_multiple_header_rows) and
                    table_id not in tables_without_data):
                    self.successes.append(f"{table_id} has proper header tags")
                
            # Warning per contenuti duplicati
            if tables_with_duplicate_headers:
                for table_id, duplicates in tables_with_duplicate_headers:
                    if duplicates:  # Only add warning if there are actual duplicates
                        self.warnings.append(f"{table_id} has duplicate headers: {', '.join(duplicates)}")
        
        if not (empty_tables or tables_without_headers or tables_without_data):
            self.check_scores['tables'] = 100
        else:
            self.check_scores['tables'] = 50

    def validate_possible_unordered_lists(self, content: List) -> None:
        """Check for consecutive paragraphs starting with '-' that might be unordered lists"""
        if not self.is_tagged:
            self.check_scores['lists'] = 0
            return
            
        def find_consecutive_dash_paragraphs(elements: List, path: str = "") -> List[List[str]]:
            sequences = []
            current_sequence = []
            
            for element in elements:
                if element['tag'] == 'P':
                    text = element.get('text', '').strip()
                    if text.startswith('-'):
                        current_sequence.append(text)
                    else:
                        if len(current_sequence) >= 2:
                            sequences.append(current_sequence.copy())
                        current_sequence = []
                
                # Check children recursively
                if element.get('children'):
                    nested_sequences = find_consecutive_dash_paragraphs(element['children'])
                    sequences.extend(nested_sequences)
            
            # Add last sequence if it exists
            if len(current_sequence) >= 2:
                sequences.append(current_sequence)
                
            return sequences
        
        sequences = find_consecutive_dash_paragraphs(content)
        
        if sequences:
            for sequence in sequences:
                self.warnings.append(
                    f"Found sequence of {len(sequence)} paragraphs that might form an unordered list"
                )
            self.check_scores['lists'] = 50
        else:
            self.check_scores['lists'] = 100

    def validate_possible_ordered_lists(self, content: List) -> None:
        """Check for consecutive paragraphs starting with sequential numbers that might be ordered lists"""
        if not self.is_tagged:
            self.check_scores['lists'] = 0
            return
            
        def find_consecutive_numbered_paragraphs(elements: List, path: str = "") -> List[List[str]]:
            sequences = []
            current_sequence = []
            
            def extract_leading_number(text: str) -> tuple[bool, int]:
                """Extract leading number from text (handles formats like '1.', '1)', '1 ')"""
                import re
                match = re.match(r'^(\d+)[.). ]', text)
                if match:
                    return True, int(match.group(1))
                return False, 0
            
            for element in elements:
                current_path = f"{path}/{element['tag']}" if path else element['tag']
                
                if element['tag'] == 'P':
                    text = element.get('text', '').strip()
                    is_numbered, number = extract_leading_number(text)
                    
                    if is_numbered:
                        if not current_sequence or number == current_sequence[-1][2] + 1:
                            current_sequence.append((current_path, text, number))
                        else:
                            if len(current_sequence) >= 2:
                                sequences.append(current_sequence.copy())
                            current_sequence = []
                            if number == 1:
                                current_sequence.append((current_path, text, number))
                    else:
                        if len(current_sequence) >= 2:
                            sequences.append(current_sequence.copy())
                        current_sequence = []
                
                # Check children recursively
                if element.get('children'):
                    nested_sequences = find_consecutive_numbered_paragraphs(element.get('children'), current_path)
                    sequences.extend(nested_sequences)
            
            # Add last sequence if it exists
            if len(current_sequence) >= 2:
                sequences.append(current_sequence)
                
            return sequences
        
        sequences = find_consecutive_numbered_paragraphs(content)
        
        if sequences:
            for sequence in sequences:
                numbers = [str(p[2]) for p in sequence]
                self.warnings.append(
                    f"Found sequence of {len(numbers)} numbered paragraphs ({', '.join(numbers)}) that might form an ordered list"
                )
            self.check_scores['lists'] = 50
        else:
            self.check_scores['lists'] = 100

    def validate_misused_unordered_lists(self, content: List) -> None:
        """Check for unordered lists containing consecutive numbered items"""
        if not self.is_tagged:
            self.check_scores['lists'] = 0
            return
            
        def extract_leading_number(text: str) -> tuple[bool, int]:
            """Extract number from text even after bullet points"""
            import re
            # Prima rimuovi eventuali bullet points (•, -, *)
            text = re.sub(r'^[•\-*]\s*', '', text.strip())
            # Poi cerca il numero
            match = re.match(r'^(\d+)[.). ]', text)
            if match:
                return True, int(match.group(1))
            return False, 0
        
        def check_list_items(element: Dict, path: str = "") -> None:
            tag = element.get('tag', '')
            current_path = f"{path}/{tag}" if path else tag
            
            if tag == 'L' and not element.get('ordered', False):  # Solo liste non ordinate
                items = element.get('items', [])
                if items:
                    current_sequence = []
                    
                    for item in items:
                        is_numbered, number = extract_leading_number(item)
                        if is_numbered:
                            if not current_sequence or number == current_sequence[-1][1] + 1:
                                current_sequence.append((item, number))
                            else:
                                if len(current_sequence) >= 2:
                                    numbers = [str(item[1]) for item in current_sequence]
                                    self.warnings.append(
                                        f"Found consecutive items numbered {', '.join(numbers)} in unordered list at: {current_path}"
                                    )
                                current_sequence = [(item, number)] if number == 1 else []
                    
                    # Check last sequence
                    if len(current_sequence) >= 2:
                        numbers = [str(item[1]) for item in current_sequence]
                        self.warnings.append(
                            f"Found consecutive items numbered {', '.join(numbers)} in unordered list at: {current_path}"
                        )
            
            # Check children recursively
            for child in element.get('children', []):
                check_list_items(child, current_path)
        
        for element in content:
            check_list_items(element)
        
        if not any(self.warnings):
            self.check_scores['lists'] = 100
        else:
            self.check_scores['lists'] = 50

    def validate_excessive_underscores(self, content: List) -> None:
        """Check recursively for excessive consecutive underscores that might be used for underlining"""
        def check_underscores(text: str) -> tuple[bool, int]:
            """Returns (has_excessive_underscores, count)"""
            import re
            # Cerca sequenze di 4 o più underscore
            pattern = r'_{4,}'
            match = re.search(pattern, text)
            if match:
                return True, len(match.group(0))
            return False, 0
            
        def check_element(element: Dict, path: str = "") -> None:
            current_path = f"{path}/{element['tag']}" if path else element['tag']
            
            # Controlla il testo dell'elemento corrente
            if 'text' in element:
                text = element.get('text', '')
                has_underscores, count = check_underscores(text)
                if has_underscores:
                    self.warnings.append(f"Found {count} consecutive underscores in {current_path} - might be attempting to create underlining")
            
            # Controlla i figli
            for child in element.get('children', []):
                check_element(child, current_path)
            
            # Per le tabelle, controlla le celle
            if element.get('tag') == 'Table':
                table_content = element.get('content', {})
                # Controlla headers
                for i, row in enumerate(table_content.get('headers', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            text = cell.get('text', '')
                            has_underscores, count = check_underscores(text)
                            if has_underscores:
                                self.warnings.append(f"Found {count} consecutive underscores in {current_path}/header[{i}][{j}] - might be attempting to create underlining")
                
                # Controlla rows
                for i, row in enumerate(table_content.get('rows', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            text = cell.get('text', '')
                            has_underscores, count = check_underscores(text)
                            if has_underscores:
                                self.warnings.append(f"Found {count} consecutive underscores in {current_path}/row[{i}][{j}] - might be attempting to create underlining")
            
            # Per le liste, controlla gli items
            if element.get('tag') == 'L':
                for i, item in enumerate(element.get('items', [])):
                    has_underscores, count = check_underscores(item)
                    if has_underscores:
                        self.warnings.append(f"Found {count} consecutive underscores in {current_path}/item[{i}] - might be attempting to create underlining")
                
        for element in content:
            check_element(element)
        
        if not any(self.warnings):
            self.check_scores['underlining'] = 100
        else:
            self.check_scores['underlining'] = 50

    def validate_spaced_capitals(self, content: List) -> None:
        """Check for words written with spaced capital letters like 'C I T T À'"""
        import re
        
        def is_spaced_capitals(text: str) -> bool:
            # Trova sequenze di lettere maiuscole separate da spazi dove ogni lettera è isolata
            # Es: "C I T T À" match, "CITTÀ" no match, "DETERMINA NOMINA" no match
            pattern = r'(?:^|\s)([A-ZÀÈÌÒÙ](?:\s+[A-ZÀÈÌÒÙ]){2,})(?:\s|$)'
            matches = re.finditer(pattern, text)
            spaced_words = []
            
            for match in matches:
                # Verifica che non ci siano lettere consecutive senza spazio
                word = match.group(1)
                if all(c == ' ' or (c.isupper() and c.isalpha()) for c in word):
                    spaced_words.append(word.strip())
                    
            return spaced_words
            
        def check_element(element: Dict, path: str = "") -> None:
            current_path = f"{path}/{element['tag']}" if path else element['tag']
            
            # Controlla il testo dell'elemento corrente
            if 'text' in element:
                text = element.get('text', '')
                spaced_words = is_spaced_capitals(text)
                if spaced_words:
                    for word in spaced_words:
                        self.warnings.append(f"Found spaced capital letters in {current_path}: '{word}'")
            
            # Controlla i figli
            for child in element.get('children', []):
                check_element(child, current_path)
            
            # Per le tabelle, controlla le celle
            if element.get('tag') == 'Table':
                table_content = element.get('content', {})
                # Controlla headers
                for i, row in enumerate(table_content.get('headers', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            text = cell.get('text', '')
                            spaced_words = is_spaced_capitals(text)
                            if spaced_words:
                                for word in spaced_words:
                                    self.warnings.append(f"Found spaced capital letters in {current_path}/header[{i}][{j}]: '{word}'")
                
                # Controlla rows
                for i, row in enumerate(table_content.get('rows', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            text = cell.get('text', '')
                            spaced_words = is_spaced_capitals(text)
                            if spaced_words:
                                for word in spaced_words:
                                    self.warnings.append(f"Found spaced capital letters in {current_path}/row[{i}][{j}]: '{word}'")
            
            # Per le liste, controlla gli items
            if element.get('tag') == 'L':
                for i, item in enumerate(element.get('items', [])):
                    spaced_words = is_spaced_capitals(item)
                    if spaced_words:
                        for word in spaced_words:
                            self.warnings.append(f"Found spaced capital letters in {current_path}/item[{i}] - might be attempting to create underlining")
                
        for element in content:
            check_element(element)
        
        if not any(self.warnings):
            self.check_scores['spacing'] = 100
        else:
            self.check_scores['spacing'] = 50

    def validate_extra_spaces(self, content: List) -> None:
        """Check for excessive spaces that might be used for layout purposes"""
        import re
        
        def check_spaces(text: str) -> List[tuple[str, int]]:
            """Returns list of (space_sequence, count) for suspicious spaces"""
            issues = []
            
            # Cerca sequenze di 3 o più spazi non a inizio/fine riga
            for match in re.finditer(r'(?<!^)\s{3,}(?!$)', text):
                space_seq = match.group()
                issues.append((space_seq, len(space_seq)))
            
            # Cerca tabulazioni multiple
            for match in re.finditer(r'\t{2,}', text):
                tab_seq = match.group()
                issues.append((tab_seq, len(tab_seq)))
            
            return issues
            
        def check_element(element: Dict, path: str = "") -> None:
            current_path = f"{path}/{element['tag']}" if path else element['tag']
            
            # Controlla il testo dell'elemento
            if 'text' in element:
                text = element.get('text', '')
                space_issues = check_spaces(text)
                if space_issues:
                    for space_seq, count in space_issues:
                        self.warnings.append(
                            f"Found {count} consecutive spaces in {current_path} - might be attempting layout with spaces"
                        )
            
            # Controlla i figli
            for child in element.get('children', []):
                check_element(child, current_path)
            
            # Controlli speciali per tabelle
            if element.get('tag') == 'Table':
                table_content = element.get('content', {})
                # Controlla headers
                for i, row in enumerate(table_content.get('headers', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            text = cell.get('text', '')
                            space_issues = check_spaces(text)
                            if space_issues:
                                for space_seq, count in space_issues:
                                    self.warnings.append(
                                        f"Found {count} consecutive spaces in {current_path}/header[{i}][{j}]"
                                    )
                
                # Controlla rows
                for i, row in enumerate(table_content.get('rows', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            text = cell.get('text', '')
                            space_issues = check_spaces(text)
                            if space_issues:
                                for space_seq, count in space_issues:
                                    self.warnings.append(
                                        f"Found {count} consecutive spaces in {current_path}/row[{i}][{j}]"
                                    )
            
            # Controlli speciali per liste
            if element.get('tag') == 'L':
                for i, item in enumerate(element.get('items', [])):
                    space_issues = check_spaces(item)
                    if space_issues:
                        for space_seq, count in space_issues:
                            self.warnings.append(
                                f"Found {count} consecutive spaces in {current_path}/item[{i}]"
                            )
                
        for element in content:
            check_element(element)
        
        if not any(self.warnings):
            self.check_scores['extra_spaces'] = 100
        else:
            extra_spaces_count = sum(1 for w in self.warnings if "consecutive spaces" in w)
            if extra_spaces_count > 10:
                self.check_scores['extra_spaces'] = 0  # Molti problemi di spaziatura
            else:
                self.check_scores['extra_spaces'] = 50  # Alcuni problemi di spaziatura

    def validate_links(self, content: List) -> None:
        """Check for non-descriptive or raw URLs in links"""
        if not self.is_tagged:
            self.check_scores['links'] = 0
            return
            
        problematic_links = []
        
        def is_problematic_link(text: str) -> tuple[bool, str]:
            """Check if link text is problematic, excluding email addresses and institutional domains"""
            import re
            
            text = text.strip().lower()
            
            # Skip check for complete email addresses
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', text):
                return False, ""
                
            # Skip check for partial email/institutional domains
            if text.endswith(('.gov.it', '.comune.it', '.it.it', '.pec.it', 
                             'pec.comune.it', '@pec.comune.it', '@comune.it')):
                return False, ""
            
            # Common problematic patterns
            patterns = {
                r'^https?://': "starts with http:// or https://",
                r'^www\.': "starts with www.",
                r'^click here$|^here$|^link$': "non-descriptive text",
                r'^[0-9]+$': "contains only numbers"
            }
            
            for pattern, reason in patterns.items():
                if re.search(pattern, text):
                    return True, reason
                    
            return False, ""
            
        def check_links_recursive(element: Dict, path: str = "", page_num: int = 1) -> None:
            # Track page numbers
            if 'Pg' in element:
                page_num = int(element['Pg'])
                
            tag = element.get('tag', '')
            current_path = f"{path}/{tag}" if path else tag
            
            # Check if element is a link
            if tag == 'Link':
                link_text = element.get('text', '').strip()
                if link_text:
                    is_bad, reason = is_problematic_link(link_text)
                    if is_bad:
                        problematic_links.append((current_path, link_text, reason, page_num))
            
            # Check children recursively
            children = element.get('children', [])
            if children:
                for child in children:
                    check_links_recursive(child, current_path, page_num)
                    
            # Special handling for table cells
            if tag == 'Table':
                table_content = element.get('content', {})
                # Check headers
                for row in table_content.get('headers', []):
                    for cell in row:
                        check_links_recursive(cell, f"{current_path}/header", page_num)
                # Check rows
                for row in table_content.get('rows', []):
                    for cell in row:
                        check_links_recursive(cell, f"{current_path}/row", page_num)
        
        # Start recursive check
        for element in content:
            check_links_recursive(element)
            
        # Update validation results
        if problematic_links:
            for path, text, reason, page in problematic_links:
                self.warnings.append(f"Non-descriptive or raw URL link on page {page}: '{text}' ({reason})")
            self.check_scores['links'] = 50
        else:
            self.check_scores['links'] = 100

    def validate_consecutive_lists(self, content: List) -> None:
        """Controlla se ci sono liste dello stesso tipo consecutive che potrebbero essere unite"""
        if not self.is_tagged:
            self.check_scores['consecutive_lists'] = 0
            return

        def find_consecutive_lists(elements: List, path: str = "", page_num: int = 1, list_counter: List[int] = [0]) -> None:
            consecutive = []
            
            # Track page changes
            if isinstance(elements, dict) and 'Pg' in elements:
                page_num = int(elements['Pg'])
            
            for i in range(len(elements)):
                current = elements[i]
                
                # Update page number if present
                if isinstance(current, dict) and 'Pg' in current:
                    page_num = int(current['Pg'])
                
                if current.get('tag') == 'L':
                    list_counter[0] += 1  # Incrementa il contatore delle liste
                    if consecutive and consecutive[-1]['type'] == current.get('ordered', False):
                        consecutive.append({
                            'list_num': list_counter[0],
                            'page': page_num,
                            'type': current.get('ordered', False),
                            'items': len(current.get('items', []))
                        })
                    else:
                        # Se abbiamo trovato una sequenza, la segnaliamo
                        if len(consecutive) > 1:
                            list_type = "ordered" if consecutive[0]['type'] else "unordered"
                            list_nums = [f"list {item['list_num']}" for item in consecutive]
                            items_count = [item['items'] for item in consecutive]
                            self.warnings.append(
                                f"Found {len(consecutive)} consecutive {list_type} lists that could be merged into one "
                                f"(Page {consecutive[0]['page']}, {', '.join(list_nums)}). "
                                f"Items per list: {items_count}"
                            )
                        consecutive = [{
                            'list_num': list_counter[0],
                            'page': page_num,
                            'type': current.get('ordered', False),
                            'items': len(current.get('items', []))
                        }]
                else:
                    # Verifica le liste consecutive trovate finora
                    if len(consecutive) > 1:
                        list_type = "ordered" if consecutive[0]['type'] else "unordered"
                        list_nums = [f"list {item['list_num']}" for item in consecutive]
                        items_count = [item['items'] for item in consecutive]
                        self.warnings.append(
                            f"Found {len(consecutive)} consecutive {list_type} lists that could be merged into one "
                            f"(page {consecutive[0]['page']}, {', '.join(list_nums)}). "
                            f"Items per list: {items_count}"
                        )
                    consecutive = []
                
                # Controlla ricorsivamente i figli
                if isinstance(current, dict) and current.get('children'):
                    find_consecutive_lists(current.get('children'), 
                                        f"{path}/{current.get('tag')}", 
                                        page_num,
                                        list_counter)
            
            # Verifica finale per l'ultima sequenza
            if len(consecutive) > 1:
                list_type = "ordered" if consecutive[0]['type'] else "unordered"
                list_nums = [f"list {item['list_num']}" for item in consecutive]
                items_count = [item['items'] for item in consecutive]
                self.warnings.append(
                    f"Found {len(consecutive)} consecutive {list_type} lists that could be merged into one "
                    f"(page {consecutive[0]['page']}, {', '.join(list_nums)}). "
                    f"Items per list: {items_count}"
                )

        # Inizializza il contatore delle liste
        list_counter = [0]
        find_consecutive_lists(content, list_counter=list_counter)
        
        if not any("consecutive" in w for w in self.warnings):
            self.check_scores['consecutive_lists'] = 100
        else:
            self.check_scores['consecutive_lists'] = 50

    def validate_italian_accents(self, content: List) -> None:
        """Check for Italian text with incorrectly used apostrophes or prime symbols instead of proper accents"""
        if not self.is_tagged:
            self.check_scores['italian_accents'] = 0
            return
            
        issues_found = []
        # Track unique issues to avoid duplicates
        unique_issues = set()
        
        # Dictionary of Italian words that frequently use accents incorrectly replaced with apostrophes
        common_accent_words = {
            # City and place names
            'citta': ('città', 'CITTÀ'),
            # Common words with final accent
            'universita': ('università', 'UNIVERSITÀ'),
            'facolta': ('facoltà', 'FACOLTÀ'),
            'liberta': ('libertà', 'LIBERTÀ'),
            'attivita': ('attività', 'ATTIVITÀ'),
            'qualita': ('qualità', 'QUALITÀ'),
            'perche': ('perché', 'PERCHÉ'),
            'poiche': ('poiché', 'POICHÉ'),
            'ne': ('né', 'NÉ'),
            'piu': ('più', 'PIÙ'),
            'cosi': ('così', 'COSÌ'),
            'lunedi': ('lunedì', 'LUNEDÌ'),
            'martedi': ('martedì', 'MARTEDÌ'),
            'mercoledi': ('mercoledì', 'MERCOLEDÌ'),
            'giovedi': ('giovedì', 'GIOVEDÌ'),
            'venerdi': ('venerdì', 'VENERDÌ'),
            'sabato': ('sabato', 'SABATO'),  # No accent
            'domenica': ('domenica', 'DOMENICA'),  # No accent
        }
        
        # All possible apostrophe/quote characters that might be used instead of an accent
        apostrophe_chars = "'\u2019\u2032\u00B4\u0060\u2035\u055A\uFF07`´"
        
        def get_quote_type(text: str) -> str:
            """Identify the type of quote character used in the text"""
            if "\u2019" in text:  # Right single quotation mark
                return "right single quotation mark (U+2019)"
            elif "\u2032" in text:  # Prime
                return "prime symbol (′)"
            elif "'" in text:  # Standard apostrophe
                return "apostrophe"
            else:
                # Identify other special characters
                for char in ["\u00B4", "\u0060", "\u2035", "\u055A", "\uFF07", "`", "´"]:
                    if char in text:
                        return f"special quote character ({char})"
            return "apostrophe"
        
        def check_text_for_accents(text: str, path: str, page_num: int = 1) -> None:
            """Analyze a text block for words that should use accents instead of apostrophes"""
            
            # Skip processing if no apostrophe-like characters present
            if not any(char in text for char in apostrophe_chars):
                return
                
            # First pass: direct word matching approach (most reliable)
            # Split text into words and check each one
            words = text.split()
            for word in words:
                # Remove surrounding punctuation but preserve internal apostrophes
                clean_word = word.strip(",.;:!?()[]{}\"")
                base_word = clean_word.rstrip(apostrophe_chars).lower()
                
                # Check if this is a common word that should have an accent
                if base_word in common_accent_words and any(char in clean_word for char in apostrophe_chars):
                    # Get the character used instead of an accent
                    quote_type = get_quote_type(clean_word)
                    
                    # Determine correct replacement based on capitalization
                    if clean_word.isupper():
                        corrected = common_accent_words[base_word][1]  # Use uppercase version
                    elif clean_word[0].isupper():
                        corrected = common_accent_words[base_word][0].capitalize()
                    else:
                        corrected = common_accent_words[base_word][0]
                        
                    # Create a unique identifier for this issue to avoid duplicates
                    issue_key = (clean_word, corrected, quote_type)
                    if issue_key not in unique_issues:
                        unique_issues.add(issue_key)
                        issues_found.append((path, clean_word, corrected, page_num, quote_type))
                    continue
            
            # Second pass: pattern-based detection for words not in our dictionary
            # Pattern for words ending with vowel + apostrophe/quote
            pattern = r'\b([a-zA-Z]+)([aeiouAEIOU])([' + re.escape(apostrophe_chars) + r'])(?:\b|$)'
            
            for match in re.finditer(pattern, text):
                word = match.group(0)
                base = match.group(1).lower()
                vowel = match.group(2).lower()
                quote_char = match.group(3)
                
                # Skip words we've already processed in the first pass
                if any(base + vowel == key for key in common_accent_words.keys()):
                    continue
                
                # Skip words that legitimately use apostrophes in Italian
                proper_apostrophe_words = ["po'", "mo'", "fa'", "va'", "da'", "sta'", 
                                          "l'", "un'", "quell'", "bell'", "buon'", "grand'", 
                                          "tutt'", "quant'", "alcun'", "ciascun'", "nessun'", "qualcun'",
                                          "dell'", "nell'", "all'", "dall'", "sull'"]
                
                if any(word.lower().startswith(proper) for proper in proper_apostrophe_words):
                    continue
                
                # Words likely to need an accent instead of apostrophe
                needs_accent = False
                
                # Check common Italian oxytone patterns (words with stress on final syllable)
                if vowel == 'a' and (base.endswith(('it', 't', 'et'))):  # -tà, -ità, etc.
                    needs_accent = True
                elif vowel == 'u' and (base.endswith(('rt', 'nt', 'v'))):  # -tù, etc.
                    needs_accent = True
                elif vowel == 'i' and (base.endswith(('d', 's', 'c'))):  # -dì, etc.
                    needs_accent = True
                elif vowel == 'e' and (base.endswith(('ch', 'rch', 'rc'))):  # -ché, etc.
                    needs_accent = True
                elif vowel == 'o' and (base.endswith(('ci', 'p', 'ro'))):  # -ciò, -però, etc.
                    needs_accent = True
                
                # Special case for uppercase words - in Italian, uppercase vowel + apostrophe
                # at end of word is almost always an accent
                if word.isupper():
                    needs_accent = True
                
                # Generate the corrected word if accent is needed
                if needs_accent:
                    accented_vowels = {
                        'a': 'à', 'e': 'è', 'i': 'ì', 'o': 'ò', 'u': 'ù',
                        'A': 'À', 'E': 'È', 'I': 'Ì', 'O': 'Ò', 'U': 'Ù'
                    }
                    
                    # Preserve original capitalization
                    if word.isupper():
                        corrected = base.upper() + accented_vowels[vowel.upper()]
                    elif word[0].isupper():
                        corrected = base.capitalize() + accented_vowels[vowel]
                    else:
                        corrected = base + accented_vowels[vowel]
                    
                    # Identify the quote character used
                    quote_type = get_quote_type(quote_char)
                    
                    # Create a unique identifier for this issue to avoid duplicates
                    issue_key = (word, corrected, quote_type)
                    if issue_key not in unique_issues:
                        unique_issues.add(issue_key)
                        issues_found.append((path, word, corrected, page_num, quote_type))
                    
            # Special case for single words like "e'" that should be "è"
            single_char_pattern = r'\b([eE])([' + re.escape(apostrophe_chars) + r'])\b'
            for match in re.finditer(single_char_pattern, text):
                word = match.group(0)
                letter = match.group(1)
                quote_char = match.group(2)
                
                corrected = 'È' if letter == 'E' else 'è'
                quote_type = get_quote_type(quote_char)
                
                # Create a unique identifier for this issue to avoid duplicates
                issue_key = (word, corrected, quote_type)
                if issue_key not in unique_issues:
                    unique_issues.add(issue_key)
                    issues_found.append((path, word, corrected, page_num, quote_type))

        def check_element(element: Dict, path: str = "", page_num: int = 1) -> None:
            # Update page number if present
            if 'Pg' in element:
                page_num = int(element['Pg'])
                
            tag = element.get('tag', '')
            current_path = f"{path}/{tag}" if path else tag
            
            # Check text content
            if 'text' in element:
                text = element.get('text', '')
                if text:
                    check_text_for_accents(text, current_path, page_num)
            
            # Check children recursively regardless of tag type
            for child in element.get('children', []):
                check_element(child, current_path, page_num)
            
            # Special handling for table structures
            if tag == 'Table':
                table_content = element.get('content', {})
                
                # Process header rows with deep inspection
                for i, row in enumerate(table_content.get('headers', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            # Check direct text content in the cell
                            text = cell.get('text', '')
                            if text:
                                check_text_for_accents(text, f"{current_path}/header[{i}][{j}]", page_num)
                            
                            # Check all nested children in the cell for accents
                            process_cell_children_deeply(cell, f"{current_path}/header[{i}][{j}]", page_num)
                
                # Process data rows with deep inspection
                for i, row in enumerate(table_content.get('rows', [])):
                    for j, cell in enumerate(row):
                        if isinstance(cell, dict):
                            # Check direct text content in the cell
                            text = cell.get('text', '')
                            if text:
                                check_text_for_accents(text, f"{current_path}/row[{i}][{j}]", page_num)
                            
                            # Check all nested children in the cell for accents
                            process_cell_children_deeply(cell, f"{current_path}/row[{i}][{j}]", page_num)
            
            # Handle list items
            if tag == 'L':
                for i, item in enumerate(element.get('items', [])):
                    check_text_for_accents(item, f"{current_path}/item[{i}]", page_num)
        
        def process_cell_children_deeply(cell: Dict, cell_path: str, page_num: int) -> None:
            """Deeply process all content in a table cell, including H1-H6 and other nested elements"""
            
            # Process direct children
            for child in cell.get('children', []):
                child_tag = child.get('tag', '')
                child_path = f"{cell_path}/{child_tag}"
                
                # Check text of any child, especially heading elements
                child_text = child.get('text', '')
                if child_text:
                    check_text_for_accents(child_text, child_path, page_num)
                
                # Process any nested children recursively
                if child.get('children'):
                    process_cell_children_deeply(child, child_path, page_num)
                
                # Special handling for nested TD/TH cells to handle double nesting
                if child_tag in ['TD', 'TH']:
                    for nested_child in child.get('children', []):
                        nested_tag = nested_child.get('tag', '')
                        nested_path = f"{child_path}/{nested_tag}"
                        
                        # Check text content
                        nested_text = nested_child.get('text', '')
                        if nested_text:
                            check_text_for_accents(nested_text, nested_path, page_num)
                        
                        # Go deeper for H1-H6, P, Span, etc.
                        process_cell_children_deeply(nested_child, nested_path, page_num)
        
        # Start recursive check for all elements in the document
        for element in content:
            check_element(element)
        
        # Store all discovered issues for detailed reporting
        accent_issues = []
        
        # Update validation results without duplicates
        if issues_found:
            # Create a set to track which warnings we've already added
            added_warnings = set()
            
            for path, wrong, correct, page, char_type in issues_found:
                # Create a warning message
                warning = f"Incorrect accent usage on page {page}: '{wrong}' should be '{correct}' ({char_type} instead of accent)"
                
                # Add the warning only if we haven't seen this exact combination before
                warning_key = (wrong, correct, char_type, page)
                if warning_key not in added_warnings:
                    added_warnings.add(warning_key)
                    self.warnings.append(warning)
                    # Add to detailed accent issues for reporting
                    accent_issues.append((page, path, wrong, correct))
            
            self.check_scores['italian_accents'] = 50
        else:
            self.check_scores['italian_accents'] = 100
            
        # Store accent issues for JSON report
        if accent_issues:
            # Sort by page number for easier reading
            accent_issues.sort(key=lambda x: x[0])
            self.accent_issues = [f"Incorrect accent usage on page {page}: '{wrong}' should be '{correct}' (at {path})" 
                                 for page, path, wrong, correct in accent_issues]
        else:
            self.accent_issues = []

    def calculate_weighted_score(self) -> float:
        """Calcola il punteggio pesato di accessibilità"""
        # Se non ci sono issues né warnings e nessun elemento vuoto, il punteggio è 100
        if not self.issues and not self.warnings and not any(value > 0 for value in self.empty_elements_count.values()):
            return 100.00

        # Se non ci sono issues né warnings ma ci sono pochi elementi vuoti (1-2),
        # il punteggio dovrebbe essere molto alto
        if not self.issues and not self.warnings:
            total_empty = self.empty_elements_count['total']
            if total_empty <= 2:
                # Calcola una piccola penalità basata sul numero di elementi vuoti
                penalty = total_empty * 0.49  # 0.49% di penalità per ogni elemento vuoto
                return 100.00 - penalty
        
        # Altrimenti calcola il punteggio pesato standard
        total_weight = sum(self.check_weights.values())
        weighted_sum = sum(
            self.check_weights[check] * self.check_scores[check]
            for check in self.check_weights
        )
        return round(weighted_sum / total_weight, 2)

    def generate_json_report(self) -> Dict:
        return {
            "validation_results": {
                "issues": self.issues,
                "warnings": self.warnings,
                "successes": self.successes,
                "weighted_score": self.calculate_weighted_score(),
                "detailed_scores": {
                    check: score for check, score in self.check_scores.items()
                },
                "accent_issues": getattr(self, 'accent_issues', [])
            }
        }

    def print_console_report(self) -> None:
        print("\n📖 Accessibility Validation Report\n")
        
        # Show successes
        if self.successes:
            print("✅ Successes:")
            for success in self.successes:
                print(f"  • {success}")
        
        # Prepare warnings, including empty elements information
        all_warnings = self.warnings.copy()
        
        # Add empty elements information to warnings in a more concise format
        if self.empty_elements_count['total'] > 0:
            # Create a detailed breakdown of empty elements
            details = []
            if self.empty_elements_count['paragraphs'] > 0:
                details.append(f"{self.empty_elements_count['paragraphs']} paragraphs")
            if self.empty_elements_count['headings'] > 0:
                details.append(f"{self.empty_elements_count['headings']} headings")
            if self.empty_elements_count['table_cells'] > 0:
                details.append(f"{self.empty_elements_count['table_cells']} table cells")
            if self.empty_elements_count['spans'] > 0:
                details.append(f"{self.empty_elements_count['spans']} spans")
            
            # Create a concise message with all details in one line
            if details:
                details_str = ", ".join(details)
                all_warnings.append(f"Found {self.empty_elements_count['total']} empty elements ({details_str})")
            else:
                all_warnings.append(f"Found {self.empty_elements_count['total']} empty elements")
        
        # Show all warnings including empty element information
        if all_warnings:
            print("\n⚠️  Warnings:")
            for warning in all_warnings:
                print(f"  • {warning}")
        
        # Show issues
        if self.issues:
            print("\n❌ Issues:")
            for issue in self.issues:
                print(f"  • {issue}")
        
        # Print summary with weighted score
        total = len(self.successes) + len(all_warnings) + len(self.issues)
        weighted_score = self.calculate_weighted_score()
        
        print(f"\n📊 Summary:")
        print(f"  • Total checks: {total}")
        print(f"  • Successes: {len(self.successes)} ✅")
        print(f"  • Warnings: {len(all_warnings)} ⚠️")  # Updated to use all_warnings
        print(f"  • Issues: {len(self.issues)} ❌")
        print(f"  • Weighted Accessibility Score: {weighted_score}%")
        
        # Overall assessment
        if weighted_score >= 90:
            print("\n🎉 Excellent! Document has very good accessibility.")
        elif weighted_score >= 70:
            print("\n👍 Good! Document has decent accessibility but could be improved.")
        elif weighted_score >= 50:
            print("\n⚠️  Fair. Document needs accessibility improvements.")
        else:
            print("\n❌ Poor. Document has serious accessibility issues.")

