from pypdf import PdfReader, PdfWriter

def merge_pdfs(pdf_list, output_path="mergedPDF.pdf"):
    merger = PdfWriter()
    for pdf in pdf_list:
        reader = PdfReader(pdf)
        merger.append_pages_from_reader(reader)
    merger.write(output_path)
    merger.close()

if __name__ == "__main__":
    # Example usage
    merge_pdfs(["testPDF1.pdf", "testPDF2.pdf"])
