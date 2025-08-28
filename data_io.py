import pandas as pd
from PyPDF2 import PdfReader

def load_table(file) -> str:
    try:
        if file.name.endswith(("xls", "xlsx")):
            df = pd.read_excel(file)
        else:
            df = pd.read_csv(file)
        return df.head(50).to_string()
    except Exception as e:
        return f"読み込み失敗: {e}"

def load_pdf(file) -> str:
    reader = PdfReader(file)
    text = ""
    for page in reader.pages[:5]:
        text += page.extract_text() or ""
    return text

def load_txt(file) -> str:
    return file.read().decode("utf-8")

def load_file(file) -> str:
    if file.name.endswith("pdf"):
        return load_pdf(file)
    elif file.name.endswith(("csv", "xls", "xlsx")):
        return load_table(file)
    else:
        return load_txt(file)