import tempfile
import urllib.parse
from pathlib import Path
import requests
import os

def is_pdf_content(data: bytes, min_size: int = 100) -> bool:
    """
    Check if the content is actually a PDF by looking at the magic number and minimum size
    """
    return len(data) >= min_size and (
        data.startswith(b'%PDF-') or 
        b'%PDF-' in data[:1024]  # Check in first 1KB for flexibility
    )

def download_pdf(url: str) -> Path:
    """Download a PDF file from URL and save it to a temporary file"""
    tmp_path = None
    try:
        # Validate URL
        parsed = urllib.parse.urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("Invalid URL")

        # Headers to simulate a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/pdf,application/x-pdf,*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
        }

        # Create session for better redirect handling
        session = requests.Session()
        
        # First make a HEAD request to check content-type and size
        head_response = session.head(url, headers=headers, allow_redirects=True, timeout=30)
        head_response.raise_for_status()
        
        # Make the actual request
        response = session.get(
            url, 
            headers=headers, 
            stream=True, 
            allow_redirects=True,
            verify=True,
            timeout=30
        )
        response.raise_for_status()

        # Create temporary file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        tmp_path = Path(tmp.name)

        # Download content in chunks
        content = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                content.extend(chunk)
                # Check first chunk for PDF signature
                if len(content) >= 8192 and not is_pdf_content(content):
                    tmp_path.unlink()
                    raise ValueError(f"Downloaded content is not a PDF file (URL after redirects: {response.url})")

        # Write content to file if it's valid
        if not is_pdf_content(content):
            tmp_path.unlink()
            raise ValueError(f"Downloaded content is not a valid PDF (size: {len(content)} bytes)")

        with open(tmp_path, 'wb') as f:
            f.write(content)

        # Verify file was written and has content
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise ValueError("Failed to write PDF file")

        return tmp_path

    except requests.exceptions.RequestException as e:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise Exception(f"Failed to download PDF: {str(e)}")
    except Exception as e:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        raise Exception(f"Failed to download PDF: {str(e)}")

def is_url(path: str) -> bool:
    """Check if the given path is a URL"""
    try:
        # Gestisce meglio gli spazi e caratteri speciali nell'URL
        path = path.strip()
        parsed = urllib.parse.urlparse(path)
        return all([parsed.scheme in ['http', 'https'], parsed.netloc])
    except:
        return False
