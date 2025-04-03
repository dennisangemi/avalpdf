import sys
from typing import Dict, List, Tuple

def extract_content(element, level=0):
    results = []
    
    # Skip if element is not a dictionary
    if not isinstance(element, dict):
        return results
        
    tag_type = element.get('S', '')
    
    try:
        # Process all tag types, including Document
        if tag_type:
            content = []
            child_elements = []
            figure_elements = []  # Track figure elements separately
            
            # Create the element base with the tag, regardless of type
            element_dict = {"tag": tag_type}
            
            # Process Figure tags with special handling for alt text
            if tag_type == 'Figure':
                alt_text = element.get('Alt', '')
                element_dict["text"] = alt_text if alt_text else ""
                results.append(element_dict)
                return results
                
            # Process Table tags with specialized extraction
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
            
            # Process list tags with special extraction 
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

            # Process all other tag types, including Document and Sect
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
                            # Check if this is a Figure tag before recursing
                            if child.get('S') == 'Figure':
                                # Keep track of figures separately to preserve their position
                                # in relation to other text content
                                figure_result = extract_content(child, level + 1)
                                if figure_result:
                                    figure_elements.append(figure_result[0])
                            else:
                                nested_results = extract_content(child, level + 1)
                                child_elements.extend(nested_results)
                
                # Extract direct content if present
                if 'Content' in element:
                    try:
                        text_fragments = extract_text_content(element.get('Content', []))
                        if text_fragments:
                            content.extend(text_fragments)
                    except (KeyError, AttributeError):
                        pass
                
                # Create element with text and children
                text = ''.join(content)
                
                if text or text == '' or figure_elements:  # Include empty strings and cases with only figures
                    element_dict["text"] = text
                    
                # Add figure elements as children if they exist
                if figure_elements:
                    if not child_elements:
                        child_elements = figure_elements
                    else:
                        # We need to merge figure_elements with child_elements
                        # in the correct order based on their position in the original document
                        # For simplicity, we'll just append them for now
                        child_elements.extend(figure_elements)
                
                if child_elements:
                    element_dict["children"] = child_elements
                    
                results.append(element_dict)
        
        # Special handling for Part, StructTreeRoot, and unlabeled elements  
        elif 'K' in element and isinstance(element.get('K'), list):
            # If there's no tag type but there are children, process them
            # This helps with unlabeled structural elements and parts
            for child in element.get('K', []):
                if isinstance(child, dict):
                    nested_results = extract_content(child, level + 1)
                    results.extend(nested_results)
                    
    except Exception as e:
        # Log the error but continue processing
        print(f"Warning: Error processing element at level {level}: {str(e)}", file=sys.stderr)
        # Add the element with error information to not lose the tag
        if tag_type:
            results.append({
                "tag": tag_type,
                "text": f"[Error extracting content: {str(e)}]",
                "extraction_error": True
            })
        
    return results

def process_table_cell(cell):
    """Process table cell content recursively"""
    if not isinstance(cell, dict):
        return [{"tag": "P", "text": ""}]
        
    cell_type = cell.get('S', '')
    if cell_type not in ['TD', 'TH']:
        return []
        
    # Create a cell element with the correct type
    cell_result = {
        "tag": cell_type,
        "text": "",  # Will be populated if there's direct text content
        "children": []  # Will be populated with nested elements
    }
    
    # Process the cell's content
    def extract_cell_elements(element, parent_element):
        if not isinstance(element, dict):
            return
            
        tag = element.get('S', '')
        
        # Special handling for Figure elements
        if tag == 'Figure':
            # Extract alt text directly
            alt_text = element.get('Alt', '')
            fig_element = {
                "tag": "Figure",
                "text": alt_text if alt_text else ""
            }
            
            # Add figure to parent's children
            if 'children' not in parent_element:
                parent_element['children'] = []
            parent_element['children'].append(fig_element)
            return
        
        # If it's a recognized structural tag, create a proper element
        if tag:
            elem_dict = {"tag": tag}
            text_content = []
            
            # Process Content directly
            if 'Content' in element:
                text_fragments = extract_text_content(element['Content'])
                text_content.extend(text_fragments)
                
            # Process children K
            child_elements = []
            if 'K' in element:
                for child in element.get('K', []):
                    # Recursive call to process nested elements
                    extract_cell_elements(child, elem_dict)
            
            # Set text for the element
            if text_content:
                elem_dict["text"] = ''.join(text_content)
                
            # Add element to parent's children
            if 'children' not in parent_element:
                parent_element['children'] = []
                
            parent_element['children'].append(elem_dict)
        else:
            # If no tag, just extract text content
            if 'Content' in element:
                text_fragments = extract_text_content(element['Content'])
                if text_fragments:
                    # Add text content to parent element
                    if 'text' not in parent_element:
                        parent_element['text'] = ''
                    parent_element['text'] += ''.join(text_fragments)
            
            # Try to process children
            if 'K' in element:
                for child in element.get('K', []):
                    extract_cell_elements(child, parent_element)
    
    # Start extracting elements from the cell
    extract_cell_elements(cell, cell_result)
    
    # If no content was extracted, return a basic paragraph
    if not cell_result.get('text') and not cell_result.get('children'):
        cell_result["text"] = ""
        
    # Mark header cells
    if cell_type == 'TH':
        cell_result["isHeader"] = True
        
    return [cell_result]

def extract_text_content(content_list):
    """Extract text content from Content list"""
    text_fragments = []
    if not isinstance(content_list, list):
        return text_fragments
        
    for content_item in content_list:
        if isinstance(content_item, dict) and content_item.get('Type') == 'Text':
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
