from PyPDF2 import PdfFileMerger


def merge_pdfs(file_list, output_path):
    merger = PdfFileMerger()
    for pdf in file_list:
        merger.append(pdf)
    merger.write(output_path)


def by_appending():
    merger = PdfFileMerger()
    f1 = open("testPDF1.pdf", "rb")
    merger.append(f1)
    merger.append("testPDF12.pdf")

    merger.write("mergedPDF.pdf")

def by_inserting():
    merger = PdfFileMerger()
    merger.append("testPDF1.pdf")
    merger.merge(0, "testPDF2.pdf")
    merger.write("mergedPDF.pdf")

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
