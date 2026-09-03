import json
import sys

sys.path.insert(0, "/home/ateeb/projects/ai-cli")
from pipeline import run_full_pipeline

files = [
    "/mnt/c/Users/ateeb/OneDrive/Documents/Documents/00. _QUARANTINE/Legacy_Metadata_Logs/Legacy_Rename_Execution_Manifest_Miscellaneous.json",
    "/mnt/c/Users/ateeb/OneDrive/Documents/Documents/00. _QUARANTINE/Legacy_Metadata_Logs/Legacy_DOCUMENT_REORGANIZATION_MASTER_GUIDE.md",
]
for f in files:
    try:
        r = run_full_pipeline(f)
        print(f"[OK] {f.split('/')[-1]}")
        print(f"  type={r['document_type']} conf={r['classification_confidence']} chars={r['chars_extracted']}")
    except Exception as e:
        print(f"[ERR] {f.split('/')[-1]}: {e}")