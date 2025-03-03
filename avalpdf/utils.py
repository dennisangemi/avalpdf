import tempfile
import urllib.request
import urllib.parse
from pathlib import Path

def download_pdf(url: str) -> Path:
    """Download a PDF file from URL and save it to a temporary file"""
    try:
        # Validate URL
        parsed = urllib.parse.urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("Invalid URL")

        # Create temporary file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        tmp_path = Path(tmp.name)

        # Download file
        urllib.request.urlretrieve(url, tmp_path)
        
        return tmp_path

    except Exception as e:
        raise Exception(f"Failed to download PDF: {str(e)}")

def is_url(path: str) -> bool:
    """Check if the given path is a URL"""
    try:
        parsed = urllib.parse.urlparse(path)
        return all([parsed.scheme, parsed.netloc])
    except:
        return False
