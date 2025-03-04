from typing import Dict, List, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich import box
from rich.table import Table as RichTable
from rich.columns import Columns
from rich.layout import Layout

console = Console()

# Color scheme for different element types
COLOR_SCHEME = {
    'P': "green",
    'H1': "red",
    'H2': "red",
    'H3': "red",
    'H4': "red",
    'H5': "red",
    'H6': "red",
    'Figure': "yellow",
    'Table': "purple",
    'L': "blue",
    'Link': "cyan",
    'Span': "white",
}

def format_element_title(element: Dict) -> Text:
    """Format the title of an element with appropriate color"""
    text = element.get('text', '').strip()
    
    title = Text()
    
    # Add full text directly without truncation or "Content:" prefix
    if text:
        title.append(f"{text}", style="dim")
    else:
        # If no text, just indicate it's an empty element
        title.append("(empty element)", style="dim italic")
    
    return title

def create_nested_panels(element: Dict) -> Panel:
    """Create nested panels to represent the tag hierarchy"""
    tag = element.get('tag', '')
    text = element.get('text', '').strip()
    children = element.get('children', [])
    
    # Get the color for this tag
    panel_style = COLOR_SCHEME.get(tag, "white")
    
    # Create content for this panel
    content = []
    
    # Add the text content if it exists, ensuring we always show paragraph text
    if text:
        content.append(Text(text))
    elif tag == 'P':
        # Se è un paragrafo vuoto ma ha dei figli, raccogliamo il testo dei figli
        child_texts = []
        for child in children:
            child_text = child.get('text', '').strip()
            if child_text:
                child_texts.append(child_text)
        
        if child_texts:
            # Mostra il testo completo del paragrafo includendo il testo dei figli
            full_text = " ".join(child_texts)
            content.append(Text(full_text))
        # Non aggiungere nessun testo se il paragrafo è vuoto

    # Special handling for links - always show URL
    if tag == 'Link':
        href = element.get('href', '')
        if href:
            content.append(Text("URL: ", style="bold") + Text(href, style="cyan"))
        elif not text:
            # Ensure even empty links have some content
            content.append(Text("(no URL)", style="dim italic"))
    
    # Continue with other special element types
    elif tag == 'Figure':
        alt_text = element.get('altText', '')
        if alt_text:
            content.append(Text("Alt Text: ", style="bold") + Text(alt_text))
    
    elif tag == 'L':
        items = element.get('items', [])
        for i, item in enumerate(items):
            # Check if the item already starts with a bullet or number
            item_text = str(item).strip()
            if element.get('ordered', False):
                # For ordered lists, check if item already starts with a number
                if not any(item_text.startswith(f"{n}.") for n in range(1, len(items) + 1)):
                    item_text = f"{i+1}. {item_text}"
            else:
                # For unordered lists, check if item already starts with a bullet
                if not item_text.startswith('•'):
                    item_text = f"• {item_text}"
            content.append(Text(item_text))
    
    elif tag == 'Table':
        # Extract table data
        table_content = element.get('content', {})
        headers = table_content.get('headers', [])
        rows = table_content.get('rows', [])
        
        # Only show warning if headers are missing
        if not headers or not any(headers):
            content.append(Text("Table without headers:", style="bold purple dim"))
        
        # Create a Rich table with better styling
        rich_table = RichTable(
            box=box.ROUNDED,
            header_style="bold purple",
            title=None,
            show_header=bool(headers and any(headers))
        )
        
        # Determine the number of columns
        num_columns = 0
        if headers and headers[0]:
            num_columns = len(headers[0])
        elif rows and rows[0]:
            num_columns = len(rows[0])
        
        # Extract header text for column names (if available)
        column_names = []
        if headers and headers[0]:
            for cell in headers[0]:
                if isinstance(cell, dict):
                    header_text = cell.get('text', '').strip() or "Header"
                    column_names.append(header_text)
                else:
                    column_names.append("Header")
        
        # Add columns with proper styling and names
        for i in range(num_columns):
            if i < len(column_names):
                column_name = column_names[i]
            else:
                column_name = f"Column {i+1}"
            rich_table.add_column(column_name, justify="left")
        
        # Skip adding header rows separately if they're already used as column headers
        # Only add additional header rows beyond the first row
        if len(headers) > 1:
            for i in range(1, len(headers)):
                row_cells = []
                for cell in headers[i]:
                    if isinstance(cell, dict):
                        cell_text = cell.get('text', '').strip() or "TH"
                        row_cells.append(Text(cell_text, style="bold"))
                    else:
                        row_cells.append("")
                if row_cells:
                    rich_table.add_row(*row_cells)
        
        # Add data rows with styled cells but avoid duplicating header content
        header_texts = set()
        if headers and headers[0]:
            for cell in headers[0]:
                if isinstance(cell, dict) and cell.get('text'):
                    header_texts.add(cell.get('text').strip())
        
        for row in rows:
            row_cells = []
            for cell in row:
                if isinstance(cell, dict):
                    is_header = cell.get('isHeader', False) or cell.get('isRowHeader', False)
                    cell_text = cell.get('text', '').strip() or "-"
                    
                    # Skip cells that duplicate header content
                    if cell_text in header_texts and is_header:
                        row_cells.append(Text("↑", style="dim"))
                    else:
                        style = "bold purple" if is_header else None
                        row_cells.append(Text(cell_text, style=style))
                else:
                    row_cells.append("")
            if row_cells:
                rich_table.add_row(*row_cells)
            
        # Only add the table if it has content
        if rich_table.row_count > 0:
            content.append(rich_table)
        else:
            content.append(Text("Empty table (no rows)", style="italic dim"))

    # Create panel for this element
    if not children:
        # If no children, create a simple panel with minimal but consistent padding
        panel_title = "Ordered List" if tag == 'L' and element.get('ordered', False) else \
                     "Unordered List" if tag == 'L' else \
                     tag
        
        # Use minimal padding but ensure consistent appearance
        padding = (0, 1)
        
        # For links, ensure they're visible but minimal
        if tag == 'Link':
            box_type = box.ROUNDED
            # Minimum width for links to ensure URLs are readable
            min_width = max(20, len(element.get('href', '')) + 6) if element.get('href') else None
        else:
            box_type = box.ROUNDED
            min_width = None
        
        return Panel(
            Columns(content, expand=False) if len(content) > 1 else (content[0] if content else ""),
            title=panel_title,
            border_style=panel_style,
            box=box_type,
            padding=padding,
            width=min_width
        )
    else:
        # Process children and create nested panels
        child_panels = []
        for child in children:
            child_panels.append(create_nested_panels(child))
        
        # Special handling to prevent P tags from wrapping links in large panels
        if tag == 'P':
            link_panels = [p for p in child_panels if p.title == "Link"]
            if link_panels:
                # Riduce il padding e la larghezza dei pannelli dei link
                for panel in link_panels:
                    panel.padding = (0, 0)  # Rimuove completamente il padding
                    # Imposta una larghezza minima più piccola
                    panel._width = min(30, len(str(panel.renderable)))
                
                # Crea un layout che mostra sia il testo del paragrafo che i link
                layout = Layout()
                
                # Se c'è contenuto del paragrafo, aggiungilo come prima sezione
                if content:
                    layout.split(
                        Layout(
                            Columns(content, expand=False),
                            name="paragraph_text",
                            ratio=1
                        )
                    )
                
                # Aggiungi i link in modo compatto
                if len(link_panels) <= 3:
                    links_layout = Layout(
                        Columns(link_panels, expand=False, padding=(0, 1)),
                        name="links"
                    )
                else:
                    links_layout = Layout(name="links")
                    for i, panel in enumerate(link_panels):
                        links_layout.add_split(Layout(panel, name=f"link_{i}"))
                
                layout.add_split(links_layout)
                layout.style = "none"
                
                return Panel(
                    layout,
                    title=tag,
                    border_style=panel_style,
                    box=box.ROUNDED,
                    padding=(0, 1),
                    width=None
                )
            else:
                # Default handling for other nested elements
                if len(child_panels) > 1:
                    nested_content = Columns(child_panels, expand=False, padding=(0, 1))
                else:
                    nested_content = child_panels[0]
        else:
            # Default handling for other element types
            if len(child_panels) > 1:
                nested_content = Columns(child_panels, expand=False, padding=(0, 1))
            else:
                nested_content = child_panels[0]
        
        # Combine current content with child panels
        if content:
            full_content = Layout()
            full_content.split(
                Layout(
                    Columns(content, expand=False) if len(content) > 1 else content[0],
                    name="element",
                    ratio=1
                ),
                Layout(nested_content, name="children", ratio=2)
            )
            full_content.style = "none"  # Remove default layout spacing
        else:
            full_content = nested_content
            
        panel_title = "Ordered List" if tag == 'L' and element.get('ordered', False) else \
                     "Unordered List" if tag == 'L' else \
                     tag
        
        # Ensure paragraphs have consistent padding
        padding = (0, 1)
        
        return Panel(
            full_content,
            title=panel_title,
            border_style=panel_style,
            box=box.ROUNDED,
            padding=padding,
            width=None  # Let Rich determine optimal width
        )

def display_document_structure(elements: List[Dict], title: str = "Document Structure"):
    """Display document structure using Rich panels and trees"""
    console.print()
    console.rule(title)
    
    # Create a legend
    legend = Panel(
        Text.from_markup(
            "Legend:\n"
            "[green]Paragraphs[/green] (P)\n"
            "[red]Headings[/red] (H1-H6)\n"
            "[yellow]Figures[/yellow] (Figure)\n"
            "[purple]Tables[/purple] (Table)\n"
            "[blue]Lists[/blue] (L)\n"
            "[cyan]Links[/cyan] (Link)"
        ),
        title="Element Types",
        border_style="dim"
    )
    console.print(legend)
    
    # Process each top-level element using the nested panel approach
    for element in elements:
        panel = create_nested_panels(element)
        console.print(panel)
    
    console.rule()
    console.print()

# Alternative tree approach - may work better in some terminals
def create_element_tree(element: Dict, tree: Optional[Tree] = None) -> Tree:
    """Recursively build a Rich Tree from a document element"""
    tag = element.get('tag', '')
    color = COLOR_SCHEME.get(tag, "white")
    
    # Create a title that includes both tag and text
    text = element.get('text', '').strip()
    title = Text()
    
    # Adjust title for lists
    if tag == 'L':
        list_type = "Ordered List" if element.get('ordered', False) else "Unordered List"
        title.append(f"{list_type}: ", style=f"{color} bold")
    else:
        title.append(f"{tag}: ", style=f"{color} bold")
    
    if text:
        title.append(f"{text}", style="dim")
    else:
        title.append("(empty element)", style="dim italic")
    
    # Create or add to tree
    if tree is None:
        tree = Tree(title)
    else:
        branch = tree.add(title)
        tree = branch
    
    # Special handling for different element types
    if tag == 'Figure':
        alt_text = element.get('altText', '')
        if alt_text:
            tree.add(Text("Alt Text: ", style="bold") + Text(alt_text))
    
    elif tag == 'Link':
        href = element.get('href', '')
        if href:
            tree.add(Text("URL: ", style="bold") + Text(href, style="cyan underline"))
        else:
            tree.add(Text("(no URL)", style="dim italic"))
    
    elif tag == 'L':
        list_type = "Ordered List" if element.get('ordered', False) else "Unordered List"
        list_branch = tree.add(Text(list_type, style="blue bold"))
        
        items = element.get('items', [])
        for i, item in enumerate(items):
            # Check if the item already starts with a bullet or number
            item_text = str(item).strip()
            if element.get('ordered', False):
                # For ordered lists, check if item already starts with a number
                if not any(item_text.startswith(f"{n}.") for n in range(1, len(items) + 1)):
                    item_text = f"{i+1}. {item_text}"
            else:
                # For unordered lists, check if item already starts with a bullet
                if not item_text.startswith('•'):
                    item_text = f"• {item_text}"
            list_branch.add(Text(item_text))
    
    elif tag == 'Table':
        table_content = element.get('content', {})
        headers = table_content.get('headers', [])
        rows = table_content.get('rows', [])
        
        # Create a Rich table with better styling
        rich_table = RichTable(
            box=box.SIMPLE,
            header_style="bold purple",
            title=None,
            show_header=bool(headers and any(headers))
        )
        
        # Determine columns 
        num_columns = 0
        if headers and headers[0]:
            num_columns = len(headers[0])
        elif rows and rows[0]:
            num_columns = len(rows[0])
        
        # Extract header text for column names (if available)
        column_names = []
        if headers and headers[0]:
            for cell in headers[0]:
                if isinstance(cell, dict):
                    header_text = cell.get('text', '').strip() or "Header"
                    column_names.append(header_text)
                else:
                    column_names.append("Header")
        
        # Add columns with proper styling and names
        for i in range(num_columns):
            if i < len(column_names):
                column_name = column_names[i]
            else:
                column_name = f"Column {i+1}"
            rich_table.add_column(column_name, justify="left")
        
        # Skip adding header rows separately if they're already used as column headers
        # Only add additional header rows beyond the first row
        if len(headers) > 1:
            for i in range(1, len(headers)):
                row_cells = []
                for cell in headers[i]:
                    if isinstance(cell, dict):
                        cell_text = cell.get('text', '').strip() or "TH"
                        row_cells.append(Text(cell_text, style="bold"))
                    else:
                        row_cells.append("")
                if row_cells:
                    rich_table.add_row(*row_cells)
        
        # Add data rows with styled cells but avoid duplicating header content
        header_texts = set()
        if headers and headers[0]:
            for cell in headers[0]:
                if isinstance(cell, dict) and cell.get('text'):
                    header_texts.add(cell.get('text').strip())
        
        for row in rows:
            row_cells = []
            for cell in row:
                if isinstance(cell, dict):
                    is_header = cell.get('isHeader', False) or cell.get('isRowHeader', False)
                    cell_text = cell.get('text', '').strip() or "-"
                    
                    # Skip cells that duplicate header content
                    if cell_text in header_texts and is_header:
                        row_cells.append(Text("↑", style="dim"))
                    else:
                        style = "bold purple" if is_header else None
                        row_cells.append(Text(cell_text, style=style))
                else:
                    row_cells.append("")
            if row_cells:
                rich_table.add_row(*row_cells)
            
        # Add the table to the tree
        if rich_table.row_count > 0:
            if not headers or not any(headers):
                table_branch = tree.add(Text("Table without headers:", style="bold purple dim"))
            else:
                table_branch = tree.add(rich_table)
                tree = table_branch
        else:
            tree.add(Text("Empty table (no rows)", style="italic dim"))
    
    # Process children recursively
    children = element.get('children', [])
    for child in children:
        create_element_tree(child, tree)
    
    return tree

def display_document_structure_tree(elements: List[Dict], title: str = "Document Structure"):
    """Display document structure using Rich trees instead of nested panels"""
    console.print()
    console.rule(title)
    
    # Create a legend
    legend = Panel(
        Text.from_markup(
            "Legend:\n"
            "[green]Paragraphs[/green] (P)\n"
            "[red]Headings[/red] (H1-H6)\n"
            "[yellow]Figures[/yellow] (Figure)\n"
            "[purple]Tables[/purple] (Table)\n"
            "[blue]Lists[/blue] (L)\n"
            "[cyan]Links[/cyan] (Link)"
        ),
        title="Element Types",
        border_style="dim"
    )
    console.print(legend)
    
    # Process each top-level element using the tree approach
    for element in elements:
        tree = create_element_tree(element)
        console.print(tree)
    
    console.rule()
    console.print()


