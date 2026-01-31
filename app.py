from flask import Flask, request, render_template, send_file, url_for, redirect, flash, session
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
import base64
import io
import shutil
import json
from flask_session import Session
try:
    from pypdf import PdfReader as NewPdfReader, PdfWriter as NewPdfWriter
except ImportError:
    NewPdfReader = PdfReader
    NewPdfWriter = PdfWriter

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

to_delete = []
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

@app.after_request
def cleanup_temp(response):
    global to_delete
    for d in to_delete:
        try:
            shutil.rmtree(d)
        except:
            pass
    to_delete.clear()
    return response

def generate_page_thumbnails(pdf_path):
    thumbnails = []
    try:
        images = convert_from_path(pdf_path, size=(200, 200))
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            thumb_data = buf.getvalue()
            thumb_b64 = base64.b64encode(thumb_data).decode()
            thumbnails.append("data:image/png;base64," + thumb_b64)
    except Exception as e:
        thumbnails = []
    return thumbnails

def generate_thumbnails(files):
    temp_dir = tempfile.mkdtemp()
    thumbnails = []
    filenames = []
    filepaths = []
    file_sizes = []
    for file in files:
        if file.filename:
            file.seek(0, 2)
            if file.tell() > MAX_FILE_SIZE:
                raise ValueError(f"File {file.filename} is too large. Maximum size is 50MB.")
            file.seek(0)
            filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            base, ext = os.path.splitext(filename)
            filename_unique = f"{base}_{unique_id}{ext}"
            filepath = os.path.join(temp_dir, filename_unique)
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
                buf = io.BytesIO()
                images[0].save(buf, format='PNG')
                thumb_data = buf.getvalue()
                thumb_b64 = base64.b64encode(thumb_data).decode()
                thumbnails.append("data:image/png;base64," + thumb_b64)
            except Exception as e:
                thumbnails.append(None)
    return thumbnails, filenames, filepaths, file_sizes, temp_dir

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/sort', methods=['GET', 'POST'])
def sort_page():
    if request.method == 'POST':
        file = request.files['pdf']
        if not file.filename:
            flash("No file selected")
            return redirect(request.url)
        file.seek(0, 2)
        if file.tell() > MAX_FILE_SIZE:
            flash("File is too large. Maximum size is 50MB.")
            return redirect(request.url)
        file.seek(0)
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        base, ext = os.path.splitext(filename)
        filename_unique = f"{base}_{unique_id}{ext}"
        temp_dir = tempfile.mkdtemp()
        filepath = os.path.join(temp_dir, filename_unique)
        file.save(filepath)
        thumbnails = generate_page_thumbnails(filepath)
        session['sort_filepath'] = filepath
        session['sort_temp_dir'] = temp_dir
        return render_template('sort.html', uploaded=True, thumbnails=thumbnails, filepath=filepath, filename=filename_unique)
    return render_template('sort.html', uploaded=False)

@app.route('/sort_pages', methods=['POST'])
def sort_pages_route():
    filepath = session.get('sort_filepath')
    temp_dir = session.get('sort_temp_dir')
    order = [int(x) for x in request.form.getlist('order')]
    if not filepath or not order or not os.path.exists(filepath):
        flash("Session expired or file not found")
        return redirect('/sort')
    temp_output_dir = tempfile.mkdtemp()
    sorted_filename = f"sorted_{uuid.uuid4()}.pdf"
    sorted_path = os.path.join(temp_output_dir, sorted_filename)
    reader = NewPdfReader(filepath)
    writer = NewPdfWriter()
    for idx in order:
        writer.add_page(reader.pages[idx])
    with open(sorted_path, "wb") as f:
        writer.write(f)
    to_delete.append(temp_dir)  # delete input after processing
    # temp_output_dir will be deleted after download
    return render_template('download.html', download_url=url_for('download', filename=sorted_filename, temp_dir=temp_output_dir), file_type='Sorted PDF', temp_dir=temp_output_dir)

@app.route('/rotate', methods=['GET', 'POST'])
def rotate_page():
    if request.method == 'POST':
        files = request.files.getlist('pdfs')
        rotation = int(request.form.get('rotation', 90))
        password = request.form.get('password', '')
        if not files or not files[0].filename:
            flash("No files selected")
            return redirect(request.url)
        temp_output_dir = tempfile.mkdtemp()
        rotated_files = []
        input_dirs = []
        for file in files:
            file.seek(0, 2)
            if file.tell() > MAX_FILE_SIZE:
                flash(f"File {file.filename} is too large.")
                continue
            file.seek(0)
            filename = secure_filename(file.filename)
            unique_id = str(uuid.uuid4())
            base, ext = os.path.splitext(filename)
            filename_unique = f"{base}_{unique_id}{ext}"
            temp_dir = tempfile.mkdtemp()
            filepath = os.path.join(temp_dir, filename_unique)
            file.save(filepath)
            input_dirs.append(temp_dir)
            rotated_filename = f"rotated_{unique_id}.pdf"
            rotated_path = os.path.join(temp_output_dir, rotated_filename)
            try:
                reader = NewPdfReader(filepath)
                writer = NewPdfWriter()
                for page in reader.pages:
                    page.rotate(rotation)
                    writer.add_page(page)
                if password:
                    writer.encrypt(password)
                with open(rotated_path, "wb") as f:
                    writer.write(f)
                rotated_files.append(rotated_filename)
            except Exception as e:
                flash(f"Error processing {file.filename}: {str(e)}")
        to_delete.extend(input_dirs)
        if not rotated_files:
            flash("No files were processed successfully.")
            return redirect(request.url)
        if len(rotated_files) == 1:
            download_url = url_for('download', filename=rotated_files[0], temp_dir=temp_output_dir)
            file_type = f'Rotated PDF ({rotation}°)'
        else:
            zip_filename = f"rotated_{uuid.uuid4()}.zip"
            zip_path = os.path.join(temp_output_dir, zip_filename)
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for rf in rotated_files:
                    zipf.write(os.path.join(temp_output_dir, rf), rf)
            download_url = url_for('download', filename=zip_filename, temp_dir=temp_output_dir)
            file_type = f'Rotated PDFs ({rotation}°) (ZIP)'
        return render_template('download.html', download_url=download_url, file_type=file_type, temp_dir=temp_output_dir)
    return render_template('rotate.html')

@app.route('/crop', methods=['GET', 'POST'])
def crop_page():
    if request.method == 'POST':
        if 'filepaths' in request.form:
            # Apply crop
            all_crop_data = json.loads(request.form['all_crop_data'])
            password = request.form.get('password', '')
            orig_width = float(request.form['orig_width'])
            orig_height = float(request.form['orig_height'])
            image_width = int(request.form['image_width'])
            image_height = int(request.form['image_height'])
            scale_x = orig_width / image_width
            scale_y = orig_height / image_height
            crop_dict = {item['page']: item for item in all_crop_data}
            filepaths = request.form.getlist('filepaths')
            if not filepaths:
                flash("No files")
                return redirect('/crop')
            temp_output_dir = tempfile.mkdtemp()
            cropped_files = []
            for fp in filepaths:
                if not os.path.exists(fp):
                    continue
                base = os.path.basename(fp)
                cropped_filename = f"cropped_{uuid.uuid4()}.pdf"
                cropped_path = os.path.join(temp_output_dir, cropped_filename)
                try:
                    reader = NewPdfReader(fp)
                    writer = NewPdfWriter()
                    for i, page in enumerate(reader.pages):
                        if i in crop_dict:
                            cd = crop_dict[i]
                            x, y, width, height = cd['x'], cd['y'], cd['width'], cd['height']
                            left = x * scale_x
                            top_crop = y * scale_y
                            right = orig_width - (x + width) * scale_x
                            bottom = orig_height - (y + height) * scale_y
                            page.mediabox.lower_left = (page.mediabox.lower_left[0] + left, page.mediabox.lower_left[1] + bottom)
                            page.mediabox.upper_right = (page.mediabox.upper_right[0] - right, page.mediabox.upper_right[1] - top_crop)
                        writer.add_page(page)
                    if password:
                        writer.encrypt(password)
                    with open(cropped_path, "wb") as f:
                        writer.write(f)
                    cropped_files.append(cropped_filename)
                except Exception as e:
                    flash(f"Error processing file: {str(e)}")
            to_delete.extend([os.path.dirname(fp) for fp in filepaths])
            if not cropped_files:
                flash("No files processed")
                return redirect('/crop')
            if len(cropped_files) == 1:
                download_url = url_for('download', filename=cropped_files[0], temp_dir=temp_output_dir)
                file_type = 'Cropped PDF'
            else:
                zip_filename = f"cropped_{uuid.uuid4()}.zip"
                zip_path = os.path.join(temp_output_dir, zip_filename)
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    for cf in cropped_files:
                        zipf.write(os.path.join(temp_output_dir, cf), cf)
                download_url = url_for('download', filename=zip_filename, temp_dir=temp_output_dir)
                file_type = 'Cropped PDFs (ZIP)'
            return render_template('download.html', download_url=download_url, file_type=file_type, temp_dir=temp_output_dir)
        else:
            # Upload and show preview
            files = request.files.getlist('pdfs')
            if not files or not files[0].filename:
                flash("No files selected")
                return redirect(request.url)
            filepaths = []
            input_dirs = []
            for file in files:
                file.seek(0, 2)
                if file.tell() > MAX_FILE_SIZE:
                    flash(f"File {file.filename} too large")
                    continue
                file.seek(0)
                filename = secure_filename(file.filename)
                unique_id = str(uuid.uuid4())
                base, ext = os.path.splitext(filename)
                filename_unique = f"{base}_{unique_id}{ext}"
                temp_dir = tempfile.mkdtemp()
                filepath = os.path.join(temp_dir, filename_unique)
                file.save(filepath)
                filepaths.append(filepath)
                input_dirs.append(temp_dir)
            if not filepaths:
                flash("No valid files")
                return redirect(request.url)
            # Use first file for preview
            first_filepath = filepaths[0]
            reader = NewPdfReader(first_filepath)
            num_pages = len(reader.pages)
            orig_width = float(reader.pages[0].mediabox.width)
            orig_height = float(reader.pages[0].mediabox.height)
            IMAGE_WIDTH = 800
            image_height = int(IMAGE_WIDTH * orig_height / orig_width)
            thumbnails = []
            full_images = []
            for i in range(num_pages):
                # Thumbnail
                thumb_image = convert_from_path(first_filepath, first_page=i+1, last_page=i+1, size=(150, 150))[0]
                thumb_buf = io.BytesIO()
                thumb_image.save(thumb_buf, format='PNG')
                thumb_b64 = base64.b64encode(thumb_buf.getvalue()).decode()
                thumbnails.append(thumb_b64)
                # Full image
                full_image = convert_from_path(first_filepath, first_page=i+1, last_page=i+1, size=(IMAGE_WIDTH, image_height))[0]
                full_filename = f'full_{i}.png'
                full_path = os.path.join(input_dirs[0], full_filename)
                full_image.save(full_path)
                full_images.append(full_filename)
            session['crop_temp_dir'] = input_dirs[0]
            session['crop_full_images'] = full_images
            # Don't delete temp_dir yet, will be deleted after processing
            return render_template('crop.html', uploaded=True, thumbnails=thumbnails, num_pages=num_pages, filepaths=filepaths, orig_width=orig_width, orig_height=orig_height, image_width=IMAGE_WIDTH, image_height=image_height)
    return render_template('crop.html', uploaded=False)

@app.route('/metadata', methods=['GET', 'POST'])
def metadata_page():
    if request.method == 'POST':
        file = request.files['pdf']
        title = request.form.get('title', '')
        author = request.form.get('author', '')
        subject = request.form.get('subject', '')
        creator = request.form.get('creator', '')
        password = request.form.get('password', '')
        if not file.filename:
            flash("No file selected")
            return redirect(request.url)
        file.seek(0, 2)
        if file.tell() > MAX_FILE_SIZE:
            flash("File is too large. Maximum size is 50MB.")
            return redirect(request.url)
        file.seek(0)
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        base, ext = os.path.splitext(filename)
        filename_unique = f"{base}_{unique_id}{ext}"
        temp_dir = tempfile.mkdtemp()
        filepath = os.path.join(temp_dir, filename_unique)
        file.save(filepath)
        temp_output_dir = tempfile.mkdtemp()
        meta_filename = f"metadata_{unique_id}.pdf"
        meta_path = os.path.join(temp_output_dir, meta_filename)
        try:
            reader = NewPdfReader(filepath)
            writer = NewPdfWriter()
            writer.add_metadata({
                '/Title': title,
                '/Author': author,
                '/Subject': subject,
                '/Creator': creator,
            })
            for page in reader.pages:
                writer.add_page(page)
            if password:
                writer.encrypt(password)
            with open(meta_path, "wb") as f:
                writer.write(f)
        except Exception as e:
            flash(f"Error processing file: {str(e)}")
            return redirect(request.url)
        to_delete.append(temp_dir)
        return render_template('download.html', download_url=url_for('download', filename=meta_filename, temp_dir=temp_output_dir), file_type='PDF with Updated Metadata', temp_dir=temp_output_dir)
    return render_template('metadata.html')

@app.route('/merge', methods=['GET', 'POST'])
def merge_page():
    if request.method == 'POST':
        files = request.files.getlist('pdfs')
        thumbnails, filenames, filepaths, file_sizes, temp_upload_dir = generate_thumbnails(files)
        # Don't delete temp_upload_dir yet
        return render_template('merge.html', uploaded=True, thumbnails=thumbnails, filenames=filenames, filepaths=filepaths)
    return render_template('merge.html', uploaded=False)

@app.route('/merge_pdfs', methods=['POST'])
def merge_pdfs_route():
    filepaths = request.form.getlist('filepaths')
    if not filepaths:
        return "No files selected", 400
    temp_output_dir = tempfile.mkdtemp()
    merged_filename = f"merged_{uuid.uuid4()}.pdf"
    merged_path = os.path.join(temp_output_dir, merged_filename)
    merge_pdfs(filepaths, merged_path)
    to_delete.extend([os.path.dirname(fp) for fp in filepaths])
    return render_template('download.html', download_url=url_for('download', filename=merged_filename, temp_dir=temp_output_dir), file_type='Merged PDF', merged_filename=merged_filename, temp_dir=temp_output_dir)

@app.route('/convert', methods=['GET', 'POST'])
def convert_page():
    if request.method == 'POST':
        files = request.files.getlist('pdfs')
        thumbnails, filenames, filepaths, file_sizes, temp_upload_dir = generate_thumbnails(files)
        # Don't delete temp_upload_dir yet
        return render_template('convert.html', uploaded=True, thumbnails=thumbnails, filenames=filenames, filepaths=filepaths)
    return render_template('convert.html', uploaded=False)

@app.route('/convert_pdfs', methods=['POST'])
def convert_pdfs_route():
    filepaths = request.form.getlist('filepaths')
    if not filepaths:
        return "No files selected", 400
    
    temp_output_dir = tempfile.mkdtemp()
    converted_files = []
    for fp in filepaths:
        pdf_path = fp
        docx_filename = os.path.basename(fp).replace('.pdf', '.docx')
        docx_path = os.path.join(temp_output_dir, docx_filename)
        
        try:
            cv = Converter(pdf_path)
            cv.convert(docx_path, start=0, end=None)
            cv.close()
            converted_files.append(docx_filename)
        except Exception as e:
            print(f"Error converting {fp}: {e}")
    
    if len(converted_files) == 1:
        download_url = url_for('download', filename=converted_files[0], temp_dir=temp_output_dir)
        to_delete.extend([os.path.dirname(fp) for fp in filepaths])
        return render_template('download.html', download_url=download_url, file_type='Word Document')
    else:
        # Create zip file
        zip_filename = f"converted_{uuid.uuid4()}.zip"
        zip_path = os.path.join(temp_output_dir, zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for docx_file in converted_files:
                zipf.write(os.path.join(temp_output_dir, docx_file), docx_file)
        download_url = url_for('download', filename=zip_filename, temp_dir=temp_output_dir)
        to_delete.extend([os.path.dirname(fp) for fp in filepaths])
        return render_template('download.html', download_url=download_url, file_type='Word Documents (ZIP)')

@app.route('/convert_merged')
def convert_merged():
    merged_filename = request.args.get('filename')
    temp_dir = request.args.get('temp_dir')
    if not merged_filename or not temp_dir:
        return "No file specified", 400

    pdf_path = os.path.join(temp_dir, merged_filename)
    docx_filename = merged_filename.replace('.pdf', '.docx')
    docx_path = os.path.join(temp_dir, docx_filename)

    try:
        cv = Converter(pdf_path)
        cv.convert(docx_path, start=0, end=None)
        cv.close()
        download_url = url_for('download', filename=docx_filename, temp_dir=temp_dir)
        return render_template('download.html', download_url=download_url, file_type='Word Document')
    except Exception as e:
        return f"Error converting file: {e}", 500

@app.route('/compress', methods=['GET', 'POST'])
def compress_page():
    if request.method == 'POST':
        files = request.files.getlist('pdfs')
        compression_level = request.form.get('compression_level', 'high')
        thumbnails, filenames, filepaths, file_sizes, temp_upload_dir = generate_thumbnails(files)
        # Don't delete temp_upload_dir yet
        return render_template('compress.html', uploaded=True, thumbnails=thumbnails, filenames=filenames, file_sizes=file_sizes, compression_level=compression_level, filepaths=filepaths)
    return render_template('compress.html', uploaded=False)

@app.route('/compress_pdfs', methods=['POST'])
def compress_pdfs_route():
    filepaths = request.form.getlist('filepaths')
    compression_level = request.form.get('compression_level', 'high')
    if not filepaths:
        return "No files selected", 400

    temp_output_dir = tempfile.mkdtemp()
    compressed_files = []
    for fp in filepaths:
        pdf_path = fp
        compressed_filename = os.path.basename(fp).replace('.pdf', '_compressed.pdf')
        compressed_path = os.path.join(temp_output_dir, compressed_filename)

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
            print(f"Compressed {fp}: {original_size} -> {compressed_size}")
            compressed_files.append(compressed_filename)
        except Exception as e:
            print(f"Error compressing {fp}: {e}")

    if not compressed_files:
        return "Error: No files were successfully compressed", 500

    if len(compressed_files) == 1:
        level_text = {'high': 'High Quality', 'medium': 'Medium Quality', 'low': 'Low Quality'}[compression_level]
        download_url = url_for('download', filename=compressed_files[0], temp_dir=temp_output_dir)
        to_delete.extend([os.path.dirname(fp) for fp in filepaths])
        return render_template('download.html', download_url=download_url, file_type=f'Compressed PDF ({level_text})')
    else:
        # Create zip file
        level_text = {'high': 'High Quality', 'medium': 'Medium Quality', 'low': 'Low Quality'}[compression_level]
        zip_filename = f"compressed_{uuid.uuid4()}.zip"
        zip_path = os.path.join(temp_output_dir, zip_filename)
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for comp_file in compressed_files:
                zipf.write(os.path.join(temp_output_dir, comp_file), comp_file)
        download_url = url_for('download', filename=zip_filename, temp_dir=temp_output_dir)
        to_delete.extend([os.path.dirname(fp) for fp in filepaths])
        return render_template('download.html', download_url=download_url, file_type=f'Compressed PDFs ({level_text}) (ZIP)')

@app.route('/compress_merged')
def compress_merged():
    merged_filename = request.args.get('filename')
    temp_dir = request.args.get('temp_dir')
    if not merged_filename or not temp_dir:
        return "No file specified", 400

    pdf_path = os.path.join(temp_dir, merged_filename)
    compressed_filename = merged_filename.replace('.pdf', '_compressed.pdf')
    compressed_path = os.path.join(temp_dir, compressed_filename)

    try:
        reader = NewPdfReader(pdf_path)
        writer = NewPdfWriter()
        writer.compress_content_streams = True

        for page in reader.pages:
            writer.add_page(page)

        with open(compressed_path, "wb") as f:
            writer.write(f)

        download_url = url_for('download', filename=compressed_filename, temp_dir=temp_dir)
        return render_template('download.html', download_url=download_url, file_type='Compressed PDF (Medium Quality)')
    except Exception as e:
        return f"Error compressing file: {e}", 500

@app.route('/preview/<filename>')
def serve_preview(filename):
    temp_dir = session.get('crop_temp_dir')
    if not temp_dir:
        return "No preview", 404
    path = os.path.join(temp_dir, filename)
    if os.path.exists(path):
        return send_file(path)
    return "Not found", 404

@app.route('/download/<filename>')
def download(filename):
    temp_dir = request.args.get('temp_dir')
    if not temp_dir:
        return "Invalid", 400
    path = os.path.join(temp_dir, filename)
    if os.path.exists(path):
        response = send_file(path, as_attachment=True)
        to_delete.append(temp_dir)  # delete after sending
        return response
    return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True)