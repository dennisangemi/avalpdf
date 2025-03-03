import json
import ctypes
from pdfixsdk import *

def pdf_to_json(pdf_path):
    """Convert PDF to JSON using PDFix SDK"""
    pdfix = GetPdfix()
    doc = pdfix.OpenDoc(pdf_path, "")
    
    if doc is None:
        raise Exception("Failed to open PDF document")
    
    # Prepare PDF to JSON conversion params
    params = PdfJsonParams()
    params.flags = (kJsonExportStructTree | kJsonExportDocInfo | kJsonExportText)
    
    # Convert to JSON
    json_conv = doc.CreateJsonConversion()
    json_conv.SetParams(params)
    
    # Extract data to stream
    mem_stm = pdfix.CreateMemStream()
    json_conv.SaveToStream(mem_stm)
    
    # Read memory stream into bytearray
    sz = mem_stm.GetSize()
    data = bytearray(sz)
    raw_data = (ctypes.c_ubyte * sz).from_buffer(data)
    mem_stm.Read(0, raw_data, len(raw_data))
    
    # Cleanup
    mem_stm.Destroy()
    doc.Close()
    
    return json.loads(data.decode("utf-8"))
