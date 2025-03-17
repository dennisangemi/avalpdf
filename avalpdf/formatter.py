from typing import Dict, List

# ANSI color codes
COLOR_GREEN = '\033[32;1m'    # P tags (verde brillante)
COLOR_RED = '\033[38;5;204m'  # Headings (rosa chiaro)
COLOR_ORANGE = '\033[33;1m'   # Figures (arancione brillante)
COLOR_PURPLE = '\033[35;1m'   # Tables (viola brillante)
COLOR_BLUE = '\033[34;1m'     # Lists (blu brillante)
COLOR_RESET = '\033[0m'       # Reset color

def print_formatted_content(element, level=0):
    """Stampa il contenuto in modo leggibile con indentazione"""
    indent = "  " * level
    
    tag = element.get('tag', '')
    text = element.get('text', '')
    children = element.get('children', [])

    # Format the tag string based on type
    if tag == 'P':
        tag_str = f"{COLOR_GREEN}[{tag}]{COLOR_RESET}"
    elif tag.startswith('H'):
        tag_str = f"{COLOR_RED}[{tag}]{COLOR_RESET}"
    elif tag == 'Figure':
        tag_str = f"{COLOR_ORANGE}[{tag}]{COLOR_RESET}"
    elif tag == 'Table':
        tag_str = f"{COLOR_PURPLE}[{tag}]{COLOR_RESET}"
    elif tag == 'L':
        tag_str = f"{COLOR_BLUE}[{tag}]{COLOR_RESET}"
    else:
        tag_str = f"[{tag}]"

    # Handle special cases
    if tag == 'Table':
        print(f"{indent}{COLOR_PURPLE}[Table]{COLOR_RESET}")
        table_content = element.get('content', {})
        
        # Obtain headers and rows to calculate optimal column width
        headers = table_content.get('headers', [])
        rows = table_content.get('rows', [])
        
        # Calculate maximum width for each column
        all_rows = headers + rows
        max_columns = max([len(row) for row in all_rows]) if all_rows else 0
        column_widths = [0] * max_columns
        
        # Determine ideal width for each column based on content
        for row in all_rows:
            for i, cell in enumerate(row):
                if i < max_columns:  # Avoid index errors
                    if isinstance(cell, dict):
                        # Calculate the length of displayed text without ANSI codes
                        formatted_content = format_cell_content_with_type(cell)
                        text_length = len(formatted_content.replace(COLOR_GREEN, "").replace(COLOR_RED, "")
                                      .replace(COLOR_ORANGE, "").replace(COLOR_PURPLE, "")
                                      .replace(COLOR_BLUE, "").replace(COLOR_RESET, ""))
                        
                        column_widths[i] = max(column_widths[i], min(text_length, 50))  # Limit to 50 chars for readability
        
        # Print headers
        if headers:
            print(f"{indent}  {COLOR_PURPLE}[Headers]{COLOR_RESET}")
            for row in headers:
                print_table_row(row, indent, column_widths, True)
            # Add a visual separator between headers and data
            separator = []
            for width in column_widths:
                separator.append("-" * width)
            print(f"{indent}    +-" + "-+-".join(separator) + "-+")
        
        # Print data rows, highlighting row headers
        if rows:
            print(f"{indent}  {COLOR_PURPLE}[Rows]{COLOR_RESET}")
            for row in rows:
                print_table_row(row, indent, column_widths)
        
        return

    if tag == 'L':
        list_type = f"{COLOR_BLUE}[ORDERED LIST]{COLOR_RESET}" if element.get('ordered', False) else f"{COLOR_BLUE}[UNORDERED LIST]{COLOR_RESET}"
        print(f"{indent}{list_type}")
        if element.get('items'):
            if element.get('ordered', False):
                for i, item in enumerate(element.get('items'), 1):
                    if not item.startswith(str(i)):
                        print(f"{indent}  {i}. {item}")
                    else:
                        print(f"{indent}  {item}")
            else:
                for item in element.get('items'):
                    print(f"{indent}  {item}")
        return

    # Special handling for elements with both text and children
    if children and text.strip():
        # Print the element's own text first
        print(f"{indent}{tag_str} {text}")
        
        # Check for Figure children
        has_figures = any(child.get('tag') == 'Figure' for child in children)
        
        # Classify children by type
        figures = []
        inline_elements = []  # Span, Link, etc.
        block_elements = []   # Other block-level elements
        
        for child in children:
            child_tag = child.get('tag', '')
            if child_tag == 'Figure':
                figures.append(child)
            elif child_tag in ['Span', 'Link']:
                inline_elements.append(child)
            else:
                block_elements.append(child)
        
        # Print inline elements on the same line
        if inline_elements:
            inline_output = []
            for child in inline_elements:
                child_tag = child.get('tag')
                child_text = child.get('text', '')
                inline_output.append(f"> [{child_tag}] {child_text}")
            
            if inline_output:
                print(f"{indent}  Inline elements: {' '.join(inline_output)}")
        
        # Print figure children with proper indentation
        if figures:
            for figure in figures:
                figure_text = figure.get('text', '')
                print(f"{indent}  {COLOR_ORANGE}[Figure]{COLOR_RESET} {figure_text}")
        
        # Print other block children recursively
        for child in block_elements:
            print_formatted_content(child, level + 1)
        
        return
        
    # Handle elements with text but no children
    elif text.strip():
        print(f"{indent}{tag_str} {text}")
        return
    
    # Handle elements with children but no text
    elif children:
        # Print the tag by itself if it has no text
        if tag != 'Sect':  # Skip empty Sect tags
            print(f"{indent}{tag_str}")
        
        # Special case for P with figure(s) only
        if tag == 'P' and all(child.get('tag') == 'Figure' for child in children):
            for child in children:
                child_text = child.get('text', '')
                print(f"{indent}  {COLOR_ORANGE}[Figure]{COLOR_RESET} {child_text}")
            return
            
        # Process all other children recursively
        for child in children:
            print_formatted_content(child, level + 1)
        return
            
    # Handle elements with neither text nor children (empty elements)
    elif tag != 'Sect':  # Skip empty Sect tags
        print(f"{indent}{tag_str}")  # Changed from print(f"{indent}{tag_str} [Empty]")

def format_cell_content_with_type(element, level=0, show_cell_type=True) -> str:
    """Format cell content recursively including cell type (TH/TD) and nested elements"""
    if not isinstance(element, dict):
        return ""
        
    tag = element.get('tag', '')
    text = element.get('text', '').strip() if element.get('text') else ""
    children = element.get('children', [])
    is_header = element.get('isHeader', False) or element.get('isRowHeader', False)
    
    # First build the main cell or element tag
    if show_cell_type and tag in ['TD', 'TH']:
        # For actual table cells
        if is_header or tag == 'TH':
            main_tag = f"{COLOR_RED}[TH]{COLOR_RESET}"
        else:
            main_tag = "[TD]"
    elif tag and tag not in ['TD', 'TH']:
        # For other elements
        if tag.startswith('H'):
            main_tag = f"{COLOR_RED}[{tag}]{COLOR_RESET}"
        elif tag == 'P':
            main_tag = f"{COLOR_GREEN}[{tag}]{COLOR_RESET}"
        elif tag == 'Figure':
            main_tag = f"{COLOR_ORANGE}[{tag}]{COLOR_RESET}"
        else:
            main_tag = f"[{tag}]"
    else:
        main_tag = ""
    
    # Build an array of parts to join later
    parts = []
    
    # First add the main tag if it exists
    if main_tag:
        parts.append(main_tag)
    
    # Add direct text if it exists
    if text:
        parts.append(text)
    
    # Now handle children (if any)
    if children:
        # Format each child without showing cell type again
        child_parts = []
        
        for child in children:
            child_tag = child.get('tag', '')
            
            # Skip nested TD/TH tags to avoid confusion
            if child_tag in ['TD', 'TH']:
                # Instead of showing the TD/TH tag again, directly show its children
                for grandchild in child.get('children', []):
                    child_str = format_cell_content_with_type(grandchild, level+1, False)
                    if child_str.strip():
                        child_parts.append(child_str)
            else:
                # For normal nested elements (not TD/TH)
                child_str = format_cell_content_with_type(child, level+1, False)
                if child_str.strip():
                    child_parts.append(child_str)
        
        # Only add child content if we have any
        if child_parts:
            # If we already have main content, add a separator
            if parts:
                return f"{' '.join(parts)} > {' > '.join(child_parts)}"
            else:
                return ' > '.join(child_parts)
    
    # If no children, just return the main parts
    return ' '.join(parts)

def print_table_row(row, indent, column_widths, is_header_row=False):
    """Print a table row with improved formatting for nested elements"""
    cells = []
    for i, cell in enumerate(row):
        if isinstance(cell, dict):
            # Format the cell content for display
            is_header = cell.get('isHeader', False) or cell.get('isRowHeader', False) or is_header_row
            
            # Improved cell formatting to properly show nested structure
            formatted_content = format_cell_content_with_type(cell)
            
            # Calculate proper width and padding
            width = column_widths[i] if i < len(column_widths) else 15
            visible_length = len(formatted_content.replace(COLOR_GREEN, "").replace(COLOR_RED, "")
                              .replace(COLOR_ORANGE, "").replace(COLOR_PURPLE, "")
                              .replace(COLOR_BLUE, "").replace(COLOR_RESET, ""))
            
            color_padding = len(formatted_content) - visible_length
            padded_content = formatted_content.ljust(width + color_padding)
            
            cells.append(padded_content)
    
    if cells:
        print(f"{indent}    | " + " | ".join(cells) + " |")

# Modifica la funzione di formato celle originale per utilizzare la nuova versione
def format_cell_content(element, level=0) -> str:
    return format_cell_content_with_type(element, level, show_cell_type=True)

def is_only_whitespace(text: str) -> bool:
    """Helper function to check if text contains only whitespace characters"""
    return bool(text and all(c in ' \t\n\r' for c in text))

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
        
    # Controlla i figli ricorsivamente, compresi gli Span
    children = element.get('children', [])
    if children:
        return all(is_element_empty(child) for child in children)
        
    # Se non ci sono né testo diretto né figli, l'elemento è vuoto
    return True
