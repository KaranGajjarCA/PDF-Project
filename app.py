from flask import Flask, request, render_template, send_file, jsonify
import os
import tempfile
import shutil
from pypdf import PdfReader, PdfWriter
import fitz
import base64
from io import BytesIO
from PIL import Image
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    files = request.files.getlist('pdfs')
    file_data = []
    existing_files = os.listdir(app.config['UPLOAD_FOLDER'])
    for file in files:
        if file.filename.endswith('.pdf'):
            if file.filename in existing_files:
                continue  # Skip duplicate
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            thumb = generate_thumbnail(filepath)
            file_data.append({'name': file.filename, 'thumb': thumb})
    return jsonify(file_data)

def generate_thumbnail(pdf_path):
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    pix = page.get_pixmap()
    img = Image.open(BytesIO(pix.tobytes()))
    img.thumbnail((100, 100))
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f'data:image/jpeg;base64,{img_str}'

@app.route('/merge', methods=['POST'])
def merge_pdfs():
    order = json.loads(request.form['order'])
    merger = PdfWriter()
    for filename in order:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            reader = PdfReader(filepath)
            merger.append_pages_from_reader(reader)
    merged_path = os.path.join(app.config['UPLOAD_FOLDER'], 'merged.pdf')
    merger.write(merged_path)
    merger.close()
    return send_file(merged_path, as_attachment=True, download_name='merged.pdf')

@app.route('/delete', methods=['POST'])
def delete_file():
    filename = request.json['filename']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({'success': True})
    return jsonify({'success': False})

if __name__ == '__main__':
    app.run(debug=True)