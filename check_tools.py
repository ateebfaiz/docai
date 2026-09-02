import importlib

tools = [
    'docling', 'rapidocr', 'paddleocr', 'paddle', 'easyocr', 'cv2',
    'torchvision', 'transformers', 'pdfplumber', 'pypdf', 'PyPDF2',
    'fitz', 'pytesseract', 'PIL', 'openpyxl', 'docx', 'xlrd',
    'camelot', 'tabula', 'dateutil', 're', 'json', 'csv',
    'sqlite3', 'numpy', 'skimage', 'pandas',
]
for t in tools:
    try:
        importlib.import_module(t)
        print('OK ', t)
    except Exception as e:
        print('NO ', t, str(e)[:80])
