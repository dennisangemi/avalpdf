import sys
from typing import Dict, List, Tuple

def extract_content(element, level=0):
    results = []
    
    # Skip if element is not a dictionary
    if not isinstance(element, dict):
        return results
        
    tag_type = element.get('S', '')
    
    try:
        # Gestione speciale per tag Part
        if tag_type == 'Part':
            if 'K' in element and isinstance(element.get('K'), list):
                for child in element.get('K', []):
                    if isinstance(child, dict):
                        nested_results = extract_content(child, level)
                        results.extend(nested_results)
            return results
            
        if tag_type and tag_type != 'Document':
            content = []
            child_elements = []
            
            # Crea l'elemento base solo con il tag
            element_dict = {"tag": tag_type}
            
            if tag_type == 'Figure':
                alt_text = element.get('Alt', '')
                element_dict["text"] = alt_text if alt_text else ""
                results.append(element_dict)
                return results
                
            elif tag_type == 'Table':
                table_content = {
                    'headers': [],
                    'rows': []
                }
                
                if 'K' in element:
                    for section in element.get('K', []):
                        if not isinstance(section, dict):
                            continue
                            
                        if section.get('S') == 'THead':
                            # Process header section
                            for row in section.get('K', []):
                                if row.get('S') == 'TR':
                                    header_row = []
                                    for cell in row.get('K', []):
                                        cell_content = process_table_cell(cell)
                                        if cell_content:
                                            header_row.extend(cell_content)
                                    if header_row:
                                        table_content['headers'].append(header_row)
                                        
                        elif section.get('S') == 'TBody':
                            # Process body section
                            for row in section.get('K', []):
                                if row.get('S') == 'TR':
                                    body_row = []
                                    has_row_header = False
                                    first_cell = True
                                    
                                    for cell in row.get('K', []):
                                        cell_content = process_table_cell(cell)
                                        if cell_content:
                                            # Identifica le celle di intestazione riga
                                            if first_cell and cell.get('S') == 'TH':
                                                has_row_header = True
                                                cell_content[0]['isRowHeader'] = True
                                            # Aggiungi le celle alla riga
                                            body_row.extend(cell_content)
                                        first_cell = False
                                        
                                    if body_row:
                                        table_content['rows'].append(body_row)
                        
                        # Handle direct TR elements (no THead/TBody structure)
                        elif section.get('S') == 'TR':
                            row_content = []
                            all_headers = True
                            
                            for cell in section.get('K', []):
                                cell_content = process_table_cell(cell)
                                if cell_content:
                                    if cell.get('S') != 'TH':
                                        all_headers = False
                                    row_content.extend(cell_content)
                                    
                            if row_content:
                                if all_headers:
                                    table_content['headers'].append(row_content)
                                else:
                                    table_content['rows'].append(row_content)
                
                results.append({
                    "tag": "Table",
                    "content": table_content
                })
                return results
            
            elif tag_type == 'Sect':
                # Estrai il contenuto direttamente dal Sect
                element_dict["text"] = ""  # Inizializza text vuoto
                
                if 'K' in element:
                    for child in element['K']:
                        child_results = extract_content(child, level + 1)
                        if child_results:
                            child_elements.extend(child_results)
                
                if child_elements:
                    element_dict["children"] = child_elements
                results.append(element_dict)
                
            elif tag_type == 'L':
                items = []
                is_ordered = False
                
                if 'K' in element:
                    for item in element.get('K', []):
                        if item.get('S') == 'LI':
                            # Estrai separatamente label e corpo dell'elemento lista
                            label = ""
                            body_text = []
                            
                            for li_child in item.get('K', []):
                                if li_child.get('S') == 'Lbl':
                                    # Estrai il bullet/numero
                                    for k in li_child.get('K', []):
                                        if isinstance(k, dict) and 'Content' in k:
                                            for content_item in k['Content']:
                                                if content_item.get('Type') == 'Text':
                                                    label += content_item.get('Text', '').strip()
                                    if label.replace('.', '').isdigit():
                                        is_ordered = True
                                        
                                elif li_child.get('S') == 'LBody':
                                    # Estrai il testo del corpo ricorsivamente preservando spazi
                                    def process_list_body(element):
                                        if isinstance(element, dict):
                                            if 'Content' in element:
                                                for content_item in element['Content']:
                                                    if content_item.get('Type') == 'Text':
                                                        text = content_item.get('Text', '')
                                                        # Aggiungi il testo senza strip() per preservare gli spazi
                                                        body_text.append(text)
                                            elif 'K' in element:
                                                for child in element['K']:
                                                    process_list_body(child)
                                    
                                    for p in li_child.get('K', []):
                                        process_list_body(p)
                                                                
                            # Combina label e body preservando gli spazi corretti
                            full_text = ''.join(body_text).strip()
                            if label and full_text:
                                items.append(f"{label} {full_text}")
                            elif full_text:
                                items.append(full_text)
                            elif label:
                                items.append(label)

                if items:
                    results.append({
                        "tag": "L",
                        "ordered": is_ordered,
                        "items": items
                    })
                return results

            else:
                # Process children first to collect nested elements
                if 'K' in element:
                    for child in element.get('K', []):
                        if not isinstance(child, dict):
                            continue
                            
                        if 'Content' in child:
                            try:
                                text_fragments = extract_text_content(child.get('Content', []))
                                if text_fragments:
                                    content.extend(text_fragments)
                            except (KeyError, AttributeError):
                                continue
                        else:
                            nested_results = extract_content(child, level + 1)
                            child_elements.extend(nested_results)
                
                # Create element with text and children
                text = ''.join(content)
                
                if text or text == '':  # Include empty strings
                    element_dict["text"] = text
                if child_elements:
                    element_dict["children"] = child_elements
                    
                results.append(element_dict)
        
        # Process siblings for Document tag
        elif 'K' in element and isinstance(element.get('K'), list):
            for child in element.get('K', []):
                if isinstance(child, dict):
                    nested_results = extract_content(child, level + 1)
                    results.extend(nested_results)
                    
    except Exception as e:
        print(f"Warning: Error processing element: {str(e)}", file=sys.stderr)
        
    return results

def process_table_cell(cell):
    """Process table cell content recursively"""
    if not isinstance(cell, dict):
        return [{"tag": "P", "text": ""}]
        
    cell_type = cell.get('S', '')
    if cell_type not in ['TD', 'TH']:
        return []
        
    # Initialize cell result
    cell_result = {"tag": "P", "text": ""}
    
    # Extract text content recursively
    def extract_cell_content(element):
        text_parts = []
        if isinstance(element, dict):
            if 'Content' in element:
                text_parts.extend(extract_text_content(element['Content']))
            if 'K' in element:
                for child in element['K']:
                    text_parts.extend(extract_cell_content(child))
        return text_parts
    
    # Get all text content from the cell
    text_parts = extract_cell_content(cell)
    cell_result["text"] = ''.join(text_parts).strip()
    
    # Mark header cells
    if cell_type == 'TH':
        cell_result["isHeader"] = True
        
    return [cell_result]

def extract_text_content(content_list):
    """Extract text content from Content list"""
    text_fragments = []
    for content_item in content_list:
        if content_item.get('Type') == 'Text':
            # Add text exactly as is, without stripping
            text_fragments.append(content_item.get('Text', ''))
    return text_fragments

def extract_list_item_text(item):
    """Helper function to extract text from list items safely"""
    try:
        if item.get('S') != 'LI':
            return None

        bullet = ""
        text_fragments = []
        
        # Extract bullet and text from LI structure
        for child in item.get('K', []):
            if child.get('S') == 'Lbl':
                # Extract bullet point
                for k in child.get('K', []):
                    if isinstance(k, dict) and 'Content' in k:
                        for content_item in k['Content']:
                            if content_item.get('Type') == 'Text':
                                bullet = content_item.get('Text', '').strip()
                                
            elif child.get('S') == 'LBody':
                # Process each paragraph in LBody
                for p in child.get('K', []):
                    if isinstance(p, dict):
                        if p.get('S') == 'P':
                            # Process paragraph content preserving spaces
                            for k in p.get('K', []):
                                if isinstance(k, dict):
                                    if 'Content' in k:
                                        # Add each text fragment, including spaces
                                        for content_item in k['Content']:
                                            if content_item.get('Type') == 'Text':
                                                text_fragments.append(content_item.get('Text', ''))
                                    elif k.get('S') in ['Span', 'Link']:
                                        for span_k in k.get('K', []):
                                            if isinstance(span_k, dict) and 'Content' in span_k:
                                                for content_item in span_k['Content']:
                                                    if content_item.get('Type') == 'Text':
                                                        text_fragments.append(content_item.get('Text', ''))

        # Join all text fragments directly, preserving spaces
        text = ''.join(text_fragments).strip()
        
        # Handle different list marker formats
        if bullet:
            if bullet in ['•', '-', '*']:  # Common bullet points
                return f"{bullet} {text}" if text else bullet
            elif bullet.isdigit() or bullet.rstrip('.').isdigit():  # Numbered lists
                return f"{bullet} {text}" if text else bullet
            else:  # Other markers
                return f"{bullet} {text}" if text else bullet
        
        return text if text else None
                
    except Exception as e:
        print(f"Warning: Error extracting list item text: {str(e)}", file=sys.stderr)
        
    return None

def create_simplified_json(pdf_json, results):
    """Create simplified JSON including metadata from full JSON"""
    metadata_fields = [
        "creation_date", "mod_date", "author", "title", "subject",
        "keywords", "producer", "creator", "standard", "lang",
        "num_pages", "tagged"
    ]
    
    simplified = {
        "metadata": {
            field: pdf_json.get(field, "") for field in metadata_fields
        },
        "content": results
    }
    return simplified
