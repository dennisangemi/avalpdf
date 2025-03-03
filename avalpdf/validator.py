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
                    
            # Special check for table cells
            if tag == 'Table':
                table_content = element.get('content', {})
                # Check both headers and rows
                for section in ['headers', 'rows']:
                    for row in table_content.get(section, []):
                        for cell in row:
                            if isinstance(cell, dict) and not cell.get('text', '').strip():
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
            
        headings = []
        empty_headings = []
        
        def collect_headings(element: Dict) -> None:
            tag = element.get('tag', '')
            if tag.startswith('H'):
                try:
                    level = int(tag[1:])
                    # Usa is_element_empty per verificare se il titolo è vuoto
                    if is_element_empty(element):
                        empty_headings.append(level)
                    else:
                        headings.append(level)
                except ValueError:
                    pass
            
            for child in element.get('children', []):
                collect_headings(child)
        
        for element in content:
            collect_headings(element)
        
        # Logica di scoring rivista per i titoli
        if empty_headings and not headings:
            # Se ci sono solo titoli vuoti, il punteggio deve essere molto basso
            self.issues.append(f"Found {len(empty_headings)} empty heading{'s' if len(empty_headings) > 1 else ''} (H{', H'.join(map(str, empty_headings))}) and no valid headings")
            self.check_scores['headings'] = 0
            return
        
        if empty_headings:
            # Se ci sono alcuni titoli vuoti ma anche titoli validi
            self.issues.append(f"Found {len(empty_headings)} empty heading{'s' if len(empty_headings) > 1 else ''} (H{', H'.join(map(str, empty_headings))})")
            self.check_scores['headings'] = 30  # Punteggio penalizzato ma non azzerato
            
        if not headings and not empty_headings:
            # Se non ci sono titoli affatto
            self.warnings.append("No headings found in document")
            self.check_scores['headings'] = 20
            return
            
        if headings:  # Verifichiamo la struttura solo se ci sono headings non vuoti
            # Controlla il livello del primo heading
            if headings[0] > 1:
                self.issues.append(f"First heading is H{headings[0]}, should be H1")
                self.check_scores['headings'] = max(self.check_scores['headings'], 40)
            
            # Controlla la gerarchia dei titoli
            prev_level = headings[0]
            hierarchy_issues = []
            
            for level in headings[1:]:  # Parti dal secondo titolo
                if level > prev_level + 1:
                    hierarchy_issues.append(f"H{prev_level} followed by H{level}")
                prev_level = level
            
            if hierarchy_issues:
                self.issues.append("Incorrect heading hierarchy: " + ", ".join(hierarchy_issues))
                self.check_scores['headings'] = max(self.check_scores['headings'], 50)
            
            if not any(issue for issue in self.issues if "heading" in issue.lower()):
                count = len(headings)
                self.successes.append(f"Found {count} heading{'s' if count > 1 else ''} with correct structure")
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
        
        # Migliorata per rilevare intestazioni sia di riga che di colonna
        def is_table_completely_empty(headers, rows) -> bool:
            # Check if all headers are empty
            all_headers_empty = all(
                not (isinstance(cell, dict) and cell.get('text', '').strip() or
                     isinstance(cell, str) and cell.strip())
                for row in headers
                for cell in row
            )
            
            # Check if all rows are empty
            all_rows_empty = all(
                not (isinstance(cell, dict) and cell.get('text', '').strip() or
                     isinstance(cell, str) and cell.strip())
                for row in rows
                for cell in row
            )
            
            return all_headers_empty and all_rows_empty
        
        def has_duplicate_headers(headers) -> tuple[bool, list]:
            if not headers:
                return False, []
            
            header_texts = []
            duplicates = []
            
            for row in headers:
                row_texts = []
                for cell in row:
                    if isinstance(cell, dict):
                        text = cell.get('text', '').strip()
                    else:
                        text = str(cell).strip()
                    if text in row_texts:
                        duplicates.append(text)
                    row_texts.append(text)
                header_texts.extend(row_texts)
            
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
            """Controlla se una cella è completamente vuota"""
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
            
            # Check data rows
            for i, row in enumerate(table_content.get('rows', [])):
                for j, cell in enumerate(row):
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
                            self.warnings.append(f"Found spaced capital letters in {current_path}/item[{i}]: '{word}'")
                
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

    def calculate_weighted_score(self) -> float:
        """Calcola il punteggio pesato di accessibilità"""
        # Se non ci sono issues né warnings, il punteggio è 100
        if not self.issues and not self.warnings and not any(value > 0 for value in self.empty_elements_count.values()):
            return 100.00
            
        # Altrimenti calcola il punteggio pesato
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
                }
            }
        }

    def print_console_report(self) -> None:
        print("\n📖 Accessibility Validation Report\n")
        
        # Print empty elements count first
        print("🔍 Empty Elements Count:")
        print(f"  • Total empty elements: {self.empty_elements_count['total']}")
        if self.empty_elements_count['paragraphs'] > 0:
            print(f"  • Empty paragraphs: {self.empty_elements_count['paragraphs']}")
        if self.empty_elements_count['table_cells'] > 0:
            print(f"  • Empty table cells: {self.empty_elements_count['table_cells']}")
        if self.empty_elements_count['headings'] > 0:
            print(f"  • Empty headings: {self.empty_elements_count['headings']}")
        if self.empty_elements_count['spans'] > 0:
            print(f"  • Empty spans: {self.empty_elements_count['spans']}")
        print()
        
        if self.successes:
            print("✅ Successes:")
            for success in self.successes:
                print(f"  • {success}")
        
        if self.warnings:
            print("\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        if self.issues:
            print("\n❌ Issues:")
            for issue in self.issues:
                print(f"  • {issue}")
        
        # Print summary with weighted score
        total = len(self.successes) + len(self.warnings) + len(self.issues)
        weighted_score = self.calculate_weighted_score()
        
        print(f"\n📊 Summary:")
        print(f"  • Total checks: {total}")
        print(f"  • Successes: {len(self.successes)} ✅")
        print(f"  • Warnings: {len(self.warnings)} ⚠️")
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

