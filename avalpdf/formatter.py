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

    # Gestione speciale per P con figura annidata
    if tag == 'P' and len(children) == 1 and children[0].get('tag') == 'Figure':
        figure = children[0]
        print(f"{indent}{COLOR_GREEN}[P]{COLOR_RESET} > {COLOR_ORANGE}[Figure]{COLOR_RESET} {figure.get('text', '')}")
        return

    # Gestione speciale per P o H con Span/Link annidati - stampa su un'unica riga
    if (tag == 'P' or tag.startswith('H')) and children:
        child_spans = [c for c in children if c.get('tag') in ['Span', 'Link']]
        if child_spans:
            # Formatta il tag principale
            if tag == 'P':
                tag_str = f"{COLOR_GREEN}[{tag}]{COLOR_RESET}"
            elif tag.startswith('H'):
                tag_str = f"{COLOR_RED}[{tag}]{COLOR_RESET}"
            else:
                tag_str = f"[{tag}]"
                
            # Formatta ogni span/link con > sulla stessa riga
            spans_output = []
            for child in child_spans:
                child_tag = child.get('tag')
                child_text = child.get('text', '')
                if child_tag == 'Span':
                    spans_output.append(f"> [Span] {child_text}")
                elif child_tag == 'Link':
                    spans_output.append(f"> [Link] {child_text}")
            
            # Stampa l'elemento principale e i suoi figli span/link sulla stessa riga
            print(f"{indent}{tag_str} {' '.join(spans_output)}")
            
            # Stampa gli altri figli che non sono Span/Link
            other_children = [c for c in children if c.get('tag') not in ['Span', 'Link']]
            for child in other_children:
                print_formatted_content(child, level + 1)
                
            return

    # Gestione tabelle migliorata con indicazione di TH e TD
    if tag == 'Table':
        print(f"{indent}{COLOR_PURPLE}[Table]{COLOR_RESET}")
        table_content = element.get('content', {})
        
        # Ottieni le intestazioni e le righe per calcolare la larghezza di colonna ottimale
        headers = table_content.get('headers', [])
        rows = table_content.get('rows', [])
        
        # Calcola la larghezza massima per ogni colonna
        all_rows = headers + rows
        max_columns = max([len(row) for row in all_rows]) if all_rows else 0
        column_widths = [0] * max_columns
        
        # Determina la larghezza ideale per ogni colonna basata sul contenuto
        for row in all_rows:
            for i, cell in enumerate(row):
                if i < max_columns:  # Evita errori di indice
                    if isinstance(cell, dict):
                        # Calcola la lunghezza del testo visualizzato senza i codici ANSI
                        text = cell.get('text', '').strip()
                        text_length = len(text)
                        
                        # Aggiungi una lunghezza extra per indicatori di TH/TD e tag annidati
                        cell_type_tag = "[TH] > " if cell.get('isHeader', False) or cell.get('isRowHeader', False) else "[TD] > "
                        tag_length = len(cell_type_tag) + 5  # [TH] > [P] è più lungo di [P]
                        total_length = text_length + tag_length
                        
                        column_widths[i] = max(column_widths[i], min(total_length, 50))  # Limita a 50 caratteri per leggibilità
        
        # Funzione per stampare una riga formattata con larghezze colonne
        def print_table_row(row, is_header_row=False):
            cells = []
            for i, cell in enumerate(row):
                if isinstance(cell, dict):
                    # Prepara il contenuto della cella con formattazione migliorata
                    is_header = cell.get('isHeader', False) or cell.get('isRowHeader', False) or is_header_row
                    
                    # Mostra sempre il tag TH o TD appropriato
                    cell_type_tag = f"{COLOR_RED}[TH]{COLOR_RESET} > " if is_header else f"[TD] > "
                    cell_content = format_cell_content_with_type(cell, show_cell_type=False).strip()
                    
                    # Combina il tag di cella con il contenuto
                    if cell_content:
                        content = f"{cell_type_tag}{cell_content}"
                    else:
                        content = f"{cell_type_tag}{COLOR_GREEN}[Empty]{COLOR_RESET}"
                    
                    # Aggiungi padding e tronca se necessario
                    width = column_widths[i] if i < len(column_widths) else 15
                    # Non consideriamo i codici ANSI nel calcolo della lunghezza
                    visible_length = len(content.replace(COLOR_GREEN, "").replace(COLOR_RED, "").
                                         replace(COLOR_ORANGE, "").replace(COLOR_PURPLE, "").
                                         replace(COLOR_BLUE, "").replace(COLOR_RESET, ""))
                    
                    # Spazio aggiuntivo per i codici di colore
                    color_padding = len(content) - visible_length
                    padded_content = content.ljust(width + color_padding)
                    
                    cells.append(padded_content)
            
            if cells:
                print(f"{indent}    | " + " | ".join(cells) + " |")
            
        # Stampa le intestazioni di colonna
        if headers:
            print(f"{indent}  {COLOR_PURPLE}[Headers]{COLOR_RESET}")
            for row in headers:
                print_table_row(row, True)
            # Aggiungi un separatore visivo tra intestazioni e dati
            separator = []
            for width in column_widths:
                separator.append("-" * width)
            print(f"{indent}    +-" + "-+-".join(separator) + "-+")
        
        # Stampa le righe di dati, evidenziando le intestazioni di riga
        if rows:
            print(f"{indent}  {COLOR_PURPLE}[Rows]{COLOR_RESET}")
            for row in rows:
                print_table_row(row)
        
        return

    # Handle other elements
    if tag == 'Figure':
        print(f"{indent}{COLOR_ORANGE}[Figure]{COLOR_RESET} {text}")
        if children:  # Process any nested elements
            for child in children:
                print_formatted_content(child, level + 1)
        return
    elif tag == 'L':
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
    elif tag == 'P':
        tag_str = f"{COLOR_GREEN}[{tag}]{COLOR_RESET}"
    elif tag.startswith('H'):
        tag_str = f"{COLOR_RED}[{tag}]{COLOR_RESET}"
    else:
        tag_str = f"[{tag}]"

    # Print current element
    if text.strip():
        print(f"{indent}{tag_str} {text}")
    elif tag != 'Sect':  # Non stampare elementi Sect vuoti
        print(f"{indent}{tag_str}")
            
    # Print children
    if children:
        for child in children:
            print_formatted_content(child, level + 1)

def format_cell_content_with_type(element, level=0, show_cell_type=True) -> str:
    """Format cell content recursively including cell type (TH/TD) and nested elements"""
    if not isinstance(element, dict):
        return ""
        
    tag = element.get('tag', '')
    text = element.get('text', '').strip()
    children = element.get('children', [])
    is_header = element.get('isHeader', False) or element.get('isRowHeader', False)
    
    parts = []
    
    # Aggiungi il tag di tipo cella (TH o TD) se richiesto
    if show_cell_type:
        if is_header:
            parts.append(f"{COLOR_RED}[TH]{COLOR_RESET} > ")
        else:
            parts.append("[TD] > ")
    
    # Casi speciali per elementi annidati
    if tag == 'P' and len(children) == 1 and children[0].get('tag') == 'Figure':
        # Per P con una sola figura annidata, mostra entrambi i tag
        figure = children[0]
        figure_part = f"{COLOR_GREEN}[P]{COLOR_RESET} > {COLOR_ORANGE}[Figure]{COLOR_RESET} {figure.get('text', '')}"
        parts.append(figure_part)
        return ''.join(parts)
    
    # Aggiungi il tag dell'elemento
    if tag == 'Figure':
        parts.append(f"{COLOR_ORANGE}[{tag}]{COLOR_RESET}")
    elif tag.startswith('H'):
        parts.append(f"{COLOR_RED}[{tag}]{COLOR_RESET}")
    elif tag == 'P':
        parts.append(f"{COLOR_GREEN}[{tag}]{COLOR_RESET}")
    else:
        parts.append(f"[{tag}]")
    
    # Aggiungi il testo dell'elemento
    if text:
        parts.append(text)
    
    # Gestione speciale per tag annidati
    if children:
        # Handle Span in P or H tags - use > syntax
        child_spans = [c for c in children if c.get('tag') in ['Span', 'Link']]
        if child_spans:
            for child in child_spans:
                child_tag = child.get('tag')
                child_text = child.get('text', '').strip() 
                if child_text:
                    parts.append(f"> [{child_tag}] {child_text}")
        
        # For other nested elements, add a compact representation
        other_children = [c for c in children if c.get('tag') not in ['Span', 'Link']]
        if other_children:
            nested_tags = [f"+{c.get('tag')}" for c in other_children]
            if nested_tags:
                parts.append(f"[{' '.join(nested_tags)}]")
    
    return ' '.join(parts)

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
