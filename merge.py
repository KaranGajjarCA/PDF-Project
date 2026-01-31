try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    from PyPDF2 import PdfReader, PdfWriter


def merge_pdfs(file_list, output_path):
    writer = PdfWriter()
    for pdf in file_list:
        reader = PdfReader(pdf)
        for page in reader.pages:
            writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    # Example usage
    merge_pdfs(["testPDF1.pdf", "testPDF2.pdf"])
