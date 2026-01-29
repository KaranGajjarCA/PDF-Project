from flask import Flask, request, render_template, send_file, url_for, redirect
import os
from werkzeug.utils import secure_filename
from merge import merge_pdfs
from pdf2image import convert_from_path
from pdf2docx import Converter
from PyPDF2 import PdfReader, PdfWriter
import fitz  # PyMuPDF
import zipfile
import tempfile
import uuid
try:
    from pypdf import PdfReader as NewPdfReader, PdfWriter as NewPdfWriter
except ImportError:
    NewPdfReader = PdfReader
    NewPdfWriter = PdfWriter

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['THUMBNAIL_FOLDER'] = 'static/thumbnails'
app.config['MERGED_FOLDER'] = 'merged'
app.config['CONVERTED_FOLDER'] = 'converted'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)
os.makedirs(app.config['MERGED_FOLDER'], exist_ok=True)
os.makedirs(app.config['CONVERTED_FOLDER'], exist_ok=True)

def generate_thumbnails(files):
    thumbnails = []
    filenames = []
    filepaths = []
    file_sizes = []
    for file in files:
        if file.filename:
            filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            base, ext = os.path.splitext(filename)
            filename_unique = f"{base}_{unique_id}{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename_unique)
            file.save(filepath)
            filepaths.append(filepath)
            filenames.append(filename_unique)
            # get file size
            size_bytes = os.path.getsize(filepath)
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024*1024:
                size_str = f"{size_bytes/1024:.1f} KB"
            else:
                size_str = f"{size_bytes/(1024*1024):.1f} MB"
            file_sizes.append(size_str)
            # generate thumbnail
            try:
                images = convert_from_path(filepath, first_page=1, last_page=1, size=(200, 200))
                thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], filename_unique.replace('.pdf', '.png'))
                images[0].save(thumb_path)
                thumbnails.append(url_for('static', filename='thumbnails/' + os.path.basename(thumb_path)))
            except Exception as e:
                thumbnails.append(None)
    return thumbnails, filenames, filepaths, file_sizes

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/merge', methods=['GET', 'POST'])
def merge_page():
    if request.method == 'POST':
        files = request.files.getlist('pdfs')
        thumbnails, filenames, filepaths, file_sizes = generate_thumbnails(files)
        return render_template('merge.html', uploaded=True, thumbnails=thumbnails, filenames=filenames)
    return render_template('merge.html', uploaded=False)

@app.route('/merge_pdfs', methods=['POST'])
def merge_pdfs_route():
    filenames = request.form.getlist('filenames')
    if not filenames:
        return "No files selected", 400
    filepaths = [os.path.join(app.config['UPLOAD_FOLDER'], fname) for fname in filenames]
    merged_filename = f"merged_{uuid.uuid4()}.pdf"
    merged_path = os.path.join(app.config['MERGED_FOLDER'], merged_filename)
    merge_pdfs(filepaths, merged_path)
    return render_template('download.html', download_url=url_for('download', filename=merged_filename), file_type='Merged PDF', merged_filename=merged_filename)

@app.route('/convert', methods=['GET', 'POST'])
def convert_page():
    if request.method == 'POST':
        files = request.files.getlist('pdfs')
        thumbnails, filenames, filepaths, file_sizes = generate_thumbnails(files)
        return render_template('convert.html', uploaded=True, thumbnails=thumbnails, filenames=filenames)
    return render_template('convert.html', uploaded=False)

@app.route('/convert_pdfs', methods=['POST'])
def convert_pdfs_route():
    filenames = request.form.getlist('filenames')
    if not filenames:
        return "No files selected", 400
    
    converted_files = []
    for fname in filenames:
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
        docx_filename = fname.replace('.pdf', '.docx')
        docx_path = os.path.join(app.config['CONVERTED_FOLDER'], docx_filename)
        
        try:
            cv = Converter(pdf_path)
            cv.convert(docx_path, start=0, end=None)
            cv.close()
            converted_files.append(docx_filename)
        except Exception as e:
            print(f"Error converting {fname}: {e}")
    
    if len(converted_files) == 1:
        return render_template('download.html', download_url=url_for('download', filename=converted_files[0]), file_type='Word Document')
    else:
        # Create zip file
        zip_filename = f"converted_{uuid.uuid4()}.zip"
        zip_path = os.path.join(app.config['MERGED_FOLDER'], zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for docx_file in converted_files:
                zipf.write(os.path.join(app.config['CONVERTED_FOLDER'], docx_file), docx_file)
        return render_template('download.html', download_url=url_for('download', filename=zip_filename), file_type='Word Documents (ZIP)')

@app.route('/convert_merged')
def convert_merged():
    merged_filename = request.args.get('filename')
    if not merged_filename:
        return "No file specified", 400

    pdf_path = os.path.join(app.config['MERGED_FOLDER'], merged_filename)
    docx_filename = merged_filename.replace('.pdf', '.docx')
    docx_path = os.path.join(app.config['CONVERTED_FOLDER'], docx_filename)

    try:
        cv = Converter(pdf_path)
        cv.convert(docx_path, start=0, end=None)
        cv.close()
        return render_template('download.html', download_url=url_for('download', filename=docx_filename), file_type='Word Document')
    except Exception as e:
        return f"Error converting file: {e}", 500

@app.route('/compress', methods=['GET', 'POST'])
def compress_page():
    if request.method == 'POST':
        files = request.files.getlist('pdfs')
        compression_level = request.form.get('compression_level', 'high')
        thumbnails, filenames, filepaths, file_sizes = generate_thumbnails(files)
        return render_template('compress.html', uploaded=True, thumbnails=thumbnails, filenames=filenames, file_sizes=file_sizes, compression_level=compression_level)
    return render_template('compress.html', uploaded=False)

@app.route('/compress_pdfs', methods=['POST'])
def compress_pdfs_route():
    filenames = request.form.getlist('filenames')
    compression_level = request.form.get('compression_level', 'high')
    if not filenames:
        return "No files selected", 400

    compressed_files = []
    for fname in filenames:
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
        compressed_filename = fname.replace('.pdf', '_compressed.pdf')
        compressed_path = os.path.join(app.config['MERGED_FOLDER'], compressed_filename)

        try:
            original_size = os.path.getsize(pdf_path)
            reader = NewPdfReader(pdf_path)
            writer = NewPdfWriter()

            # Set compression based on level
            if compression_level == 'low':
                writer.compress_content_streams = True
                # For low, also remove images or compress, but for now, just compress streams
            elif compression_level == 'medium':
                writer.compress_content_streams = True
            # High: no compression

            for page in reader.pages:
                writer.add_page(page)

            with open(compressed_path, "wb") as f:
                writer.write(f)

            compressed_size = os.path.getsize(compressed_path)
            print(f"Compressed {fname}: {original_size} -> {compressed_size}")
            compressed_files.append(compressed_filename)
        except Exception as e:
            print(f"Error compressing {fname}: {e}")

    if not compressed_files:
        return "Error: No files were successfully compressed", 500

    if len(compressed_files) == 1:
        level_text = {'high': 'High Quality', 'medium': 'Medium Quality', 'low': 'Low Quality'}[compression_level]
        return render_template('download.html', download_url=url_for('download', filename=compressed_files[0]), file_type=f'Compressed PDF ({level_text})')
    else:
        # Create zip file
        level_text = {'high': 'High Quality', 'medium': 'Medium Quality', 'low': 'Low Quality'}[compression_level]
        zip_filename = f"compressed_{uuid.uuid4()}.zip"
        zip_path = os.path.join(app.config['MERGED_FOLDER'], zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for comp_file in compressed_files:
                zipf.write(os.path.join(app.config['MERGED_FOLDER'], comp_file), comp_file)
        return render_template('download.html', download_url=url_for('download', filename=zip_filename), file_type=f'Compressed PDFs ({level_text}) (ZIP)')

@app.route('/compress_merged')
def compress_merged():
    merged_filename = request.args.get('filename')
    if not merged_filename:
        return "No file specified", 400

    pdf_path = os.path.join(app.config['MERGED_FOLDER'], merged_filename)
    compressed_filename = merged_filename.replace('.pdf', '_compressed.pdf')
    compressed_path = os.path.join(app.config['MERGED_FOLDER'], compressed_filename)

    try:
        reader = NewPdfReader(pdf_path)
        writer = NewPdfWriter()
        writer.compress_content_streams = True

        for page in reader.pages:
            writer.add_page(page)

        with open(compressed_path, "wb") as f:
            writer.write(f)

        return render_template('download.html', download_url=url_for('download', filename=compressed_filename), file_type='Compressed PDF (Medium Quality)')
    except Exception as e:
        return f"Error compressing file: {e}", 500

@app.route('/download/<filename>')
def download(filename):
    # Check in merged folder first
    path = os.path.join(app.config['MERGED_FOLDER'], filename)
    if not os.path.exists(path):
        # Check in converted folder
        path = os.path.join(app.config['CONVERTED_FOLDER'], filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True)