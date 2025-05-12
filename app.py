from flask import Flask, render_template, request, jsonify, send_file, session
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import json
from extensions import db
from file_handler import FileHandler
from nlp_processor import NLPProcessor
from wer_calculator import WERCalculator
from pydub import AudioSegment
import io
import re
import whisper

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'  # Change this in production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///wer_analysis.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

# Import models after db initialization
from models import Transcription

model = whisper.load_model("base")  # or your preferred model size

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/wer-analysis')
def wer_analysis():
    return render_template('wer_analysis.html')

@app.route('/history')
def history():
    transcriptions = Transcription.query.order_by(Transcription.created_at.desc()).all()
    return render_template('history.html', transcriptions=transcriptions)

@app.route('/api/transcribe', methods=['POST'])
def transcribe():
    handler = FileHandler(app.config['UPLOAD_FOLDER'])
    # Step 1: File upload
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        filename = secure_filename(file.filename)
        # If webm, convert to wav and transcribe directly
        if filename.endswith('.webm'):
            try:
                audio = AudioSegment.from_file(file, format='webm')
                wav_io = io.BytesIO()
                audio.export(wav_io, format='wav')
                wav_io.seek(0)
                # Save to temp file for Whisper
                temp_wav_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_recording.wav')
                with open(temp_wav_path, 'wb') as f:
                    f.write(wav_io.read())
                text = handler.extract_text_from_audio(temp_wav_path)
                os.remove(temp_wav_path)
                return jsonify({'status': 'success', 'text': text})
            except Exception as e:
                return jsonify({'error': f'Failed to process webm audio: {str(e)}'}), 500
        file_path = handler.save_file(file, filename)
        if not file_path:
            return jsonify({'error': 'File could not be saved'}), 500
        session['uploaded_filename'] = filename
        return jsonify({'status': 'success', 'message': 'File uploaded'})
    # Step 2: Transcribe
    filename = session.get('uploaded_filename')
    if not filename:
        return jsonify({'error': 'No file uploaded in session'}), 400
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found on server'}), 404
    result = handler.process_file(file_path)
    if 'error' in result and result['error']:
        return jsonify({'status': 'error', 'message': result['error']}), 400
    text = result['text']
    return jsonify({'status': 'success', 'text': text})

@app.route('/api/whisper-transcribe', methods=['POST'])
def whisper_transcribe():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded.'}), 400
    file = request.files['file']
    temp_path = 'temp_audio.wav'
    file.save(temp_path)
    try:
        result = model.transcribe(temp_path)
        return jsonify({'status': 'success', 'text': result['text']})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
    text = re.sub(r'\s+', ' ', text).strip()  # Normalize whitespace
    return text

@app.route('/api/calculate-wer', methods=['POST'])
def calculate_wer():
    data = request.json
    transcribed_text = data.get('transcribed_text', '')
    reference_text = data.get('reference_text', '')
    transcribed_nlp = data.get('transcribed_nlp')
    reference_nlp = data.get('reference_nlp')

    print('Transcribed:', transcribed_text)
    print('Reference:', reference_text)

    if not transcribed_text or not reference_text:
        return jsonify({'status': 'error', 'message': 'Both texts are required'}), 400

    # Normalize both texts before WER calculation
    ref_norm = normalize_text(reference_text)
    hyp_norm = normalize_text(transcribed_text)

    wer_calc = WERCalculator()
    analysis = wer_calc.analyze_texts(ref_norm, hyp_norm)

    # Add word difference list and statistics for the frontend
    ref_words = wer_calc.transformation(ref_norm)
    hyp_words = wer_calc.transformation(hyp_norm)

    # Word difference list (simple diff for now)
    import difflib
    diff = list(difflib.ndiff(ref_words, hyp_words))
    word_differences = []
    for d in diff:
        if d.startswith('- '):
            word_differences.append({'type': 'deleted', 'text': d[2:]})
        elif d.startswith('+ '):
            word_differences.append({'type': 'inserted', 'text': d[2:]})
        elif d.startswith('? '):
            continue
        else:
            word_differences.append({'type': 'normal', 'text': d[2:]})

    # Statistics
    statistics = {
        'Word Count': {
            'transcribed': len(hyp_words),
            'reference': len(ref_words)
        },
        'Unique Words': {
            'transcribed': len(set(hyp_words)),
            'reference': len(set(ref_words))
        }
    }

    # Prepare plots for frontend (convert Plotly figures to JSON)
    from plotly.utils import PlotlyJSONEncoder
    import json as pyjson
    plots = analysis['plots']
    plots_json = {}
    for key, fig in plots.items():
        plots_json[key] = pyjson.loads(pyjson.dumps(fig, cls=PlotlyJSONEncoder))
    
    results = {
        'wer_score': analysis['wer_score'],
        'differences': analysis['differences'],
        'word_differences': word_differences,
        'statistics': statistics,
        'plots': plots_json,
        'nlp_results': {
            'transcribed': transcribed_nlp if transcribed_nlp is not None else pyjson.loads(session.get('transcribedNLP', '{}')),
            'reference': reference_nlp if reference_nlp is not None else pyjson.loads(session.get('referenceNLP', '{}'))
        }
    }
    return jsonify({'status': 'success', 'results': results})

@app.route('/api/save-analysis', methods=['POST'])
def save_analysis():
    data = request.json
    print('SAVE ANALYSIS PAYLOAD:', data)
    filename = data.get('filename', 'Analysis')
    transcribed_text = data.get('transcribed_text', '')
    reference_text = data.get('reference_text', '')
    wer_results = data.get('wer_results', {})
    nlp_results = data.get('nlp_results', {})
    file_metadata = data.get('file_metadata', {})
    # Ensure created date in file_metadata
    if not file_metadata.get('created'):
        file_metadata['created'] = datetime.now().isoformat()
    # Use provided file_metadata if available, fallback only if missing fields
    if file_metadata:
        # Fill missing fields if any
        if not file_metadata.get('filename') or not file_metadata.get('type') or not file_metadata.get('size'):
            if 'recording' in filename.lower() or filename.lower().endswith('.webm'):
                file_metadata['filename'] = file_metadata.get('filename', 'Voice Recording')
                file_metadata['extension'] = file_metadata.get('extension', 'webm')
                file_metadata['type'] = file_metadata.get('type', 'Audio')
                file_metadata['size'] = file_metadata.get('size', len(transcribed_text.encode('utf-8')))
            else:
                ext = filename.split('.')[-1].lower() if '.' in filename else ''
                file_metadata['filename'] = file_metadata.get('filename', filename)
                file_metadata['extension'] = file_metadata.get('extension', ext)
                if ext in ['mp3', 'wav', 'webm']:
                    file_metadata['type'] = file_metadata.get('type', 'Audio')
                elif ext in ['mp4', 'mkv']:
                    file_metadata['type'] = file_metadata.get('type', 'Video')
                elif ext in ['jpg', 'jpeg', 'png']:
                    file_metadata['type'] = file_metadata.get('type', 'Image')
                else:
                    file_metadata['type'] = file_metadata.get('type', 'Unknown')
                if not file_metadata.get('size'):
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    if os.path.exists(file_path):
                        file_metadata['size'] = os.path.getsize(file_path)
                    else:
                        file_metadata['size'] = len(transcribed_text.encode('utf-8'))
    else:
        file_metadata = {}
        if 'recording' in filename.lower() or filename.lower().endswith('.webm'):
            file_metadata['filename'] = 'Voice Recording'
            file_metadata['extension'] = 'webm'
            file_metadata['type'] = 'Audio'
            file_metadata['size'] = len(transcribed_text.encode('utf-8'))
        else:
            ext = filename.split('.')[-1].lower() if '.' in filename else ''
            file_metadata['filename'] = filename
            file_metadata['extension'] = ext
            if ext in ['mp3', 'wav', 'webm']:
                file_metadata['type'] = 'Audio'
            elif ext in ['mp4', 'mkv']:
                file_metadata['type'] = 'Video'
            elif ext in ['jpg', 'jpeg', 'png']:
                file_metadata['type'] = 'Image'
            else:
                file_metadata['type'] = 'Unknown'
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                file_metadata['size'] = os.path.getsize(file_path)
            else:
                file_metadata['size'] = len(transcribed_text.encode('utf-8'))
    # After finalizing file_metadata, set the top-level filename to match file_metadata['filename'] if present
    filename = file_metadata.get('filename', filename)
    # Ensure differences, word_differences, statistics are present
    differences = wer_results.get('differences', [])
    word_differences = wer_results.get('word_differences', [])
    statistics = wer_results.get('statistics', {})
    plots = wer_results.get('plots', {
        'confusion_matrix': {'data': [], 'layout': {}},
        'word_count_comparison': {'data': [], 'layout': {}},
        'statistics_plot': {'data': [], 'layout': {}},
        'radar_chart': {'data': [], 'layout': {}}
    })
    wer_score = wer_results.get('wer_score', 0.0)
    analysis_results = {
        'wer_score': wer_score,
        'differences': differences,
        'word_differences': word_differences,
        'statistics': statistics,
        'plots': plots
    }
    transcription = Transcription(
        filename=filename,
        transcribed_text=transcribed_text,
        reference_text=reference_text,
        wer_score=wer_score,
        nlp_results=json.dumps(nlp_results),
        analysis_results=json.dumps(analysis_results),
        file_metadata=json.dumps(file_metadata)
    )
    db.session.add(transcription)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Analysis saved'})

@app.route('/api/history', methods=['GET'])
def api_history():
    transcriptions = Transcription.query.order_by(Transcription.created_at.desc()).all()
    return jsonify({'status': 'success', 'analyses': [t.to_dict() for t in transcriptions]})

@app.route('/api/delete-analysis/<int:id>', methods=['DELETE'])
def delete_analysis(id):
    transcription = Transcription.query.get_or_404(id)
    db.session.delete(transcription)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Analysis deleted'})

@app.route('/api/process-reference', methods=['POST'])
def process_reference():
    handler = FileHandler(app.config['UPLOAD_FOLDER'])
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    filename = secure_filename(file.filename)
    file_path = handler.save_file(file, filename)
    if not file_path:
        return jsonify({'error': 'File could not be saved'}), 500
    result = handler.process_file(file_path)
    text = result['text']
    return jsonify({'status': 'success', 'text': text})

@app.route('/api/preprocess', methods=['POST'])
def preprocess():
    data = request.get_json()
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    processor = NLPProcessor()
    results = processor.process_text(text)
    return jsonify({'status': 'success', 'results': results})

@app.route('/api/get-analysis/<int:id>', methods=['GET'])
def get_analysis(id):
    transcription = Transcription.query.get_or_404(id)
    analysis = transcription.to_dict()
    # Extract WER and NLP results
    wer_results = analysis['analysis_results'] or {}
    nlp_results = analysis['nlp_results'] or {'transcribed': {}, 'reference': {}}
    # Compose response to match /api/calculate-wer structure
    response = {
        'id': analysis['id'],
        'filename': analysis['filename'],
        'created_at': analysis['created_at'],
        'transcribed_text': analysis['transcribed_text'],
        'reference_text': analysis['reference_text'],
        'wer_score': wer_results.get('wer_score', analysis['wer_score']),
        'differences': wer_results.get('differences', []),
        'word_differences': wer_results.get('word_differences', []),
        'statistics': wer_results.get('statistics', {}),
        'plots': wer_results.get('plots', {
            'confusion_matrix': {'data': [], 'layout': {}},
            'word_count_comparison': {'data': [], 'layout': {}},
            'statistics_plot': {'data': [], 'layout': {}},
            'radar_chart': {'data': [], 'layout': {}}
        }),
        'nlp_results': nlp_results,
        'metadata': analysis['file_metadata'] or {}
    }
    return jsonify({'status': 'success', 'analysis': response})

@app.route('/api/get-history', methods=['GET'])
def get_history():
    transcriptions = Transcription.query.order_by(Transcription.created_at.desc()).all()
    analyses = []
    from datetime import datetime
    for t in transcriptions:
        d = t.to_dict()
        # Parse metadata for sidebar
        try:
            metadata = json.loads(d['file_metadata']) if d['file_metadata'] else {}
        except Exception:
            metadata = {}
        # Parse plots for sidebar (just WER score and filename)
        try:
            analysis_results = json.loads(d['analysis_results']) if d['analysis_results'] else {}
        except Exception:
            analysis_results = {}
        # Use friendlier label for filename
        filename = metadata.get('filename') or d.get('filename') or 'Manual Analysis'
        # Always set a creation date
        created = metadata.get('created') or d.get('created_at') or datetime.now().isoformat()
        try:
            created_str = (datetime.fromisoformat(created).isoformat() if created else None)
        except Exception:
            created_str = None
        analyses.append({
            'id': d.get('id'),
            'wer_score': float(analysis_results.get('wer_score', d.get('wer_score', 0.0)) or 0.0),
            'metadata': {
                'filename': filename,
                'created': created_str,
                'extension': metadata.get('extension', 'N/A'),
                'size': metadata.get('size', 'N/A')
            },
        })
    return jsonify({'status': 'success', 'analyses': analyses})

@app.route('/api/delete-all-analyses', methods=['DELETE'])
def delete_all_analyses():
    Transcription.query.delete()
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'All analyses deleted'})

@app.route('/api/download-pdf/<int:id>', methods=['GET'])
def download_pdf(id):
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib import colors
    import plotly.io as pio
    transcription = Transcription.query.get_or_404(id)
    analysis = transcription.to_dict()
    # Fix: Only json.loads if needed
    analysis_results_raw = analysis['analysis_results']
    if isinstance(analysis_results_raw, str):
        wer_results = json.loads(analysis_results_raw) if analysis_results_raw else {}
    else:
        wer_results = analysis_results_raw if analysis_results_raw else {}
    nlp_results_raw = analysis['nlp_results']
    if isinstance(nlp_results_raw, str):
        nlp_results = json.loads(nlp_results_raw) if nlp_results_raw else {}
    else:
        nlp_results = nlp_results_raw if nlp_results_raw else {}
    plots = wer_results.get('plots', {})
    # Create PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40
    # Helper for section headings
    def section_heading(text, y, c, width, size=15):
        c.setFont('Helvetica-Bold', size)
        c.drawString(30, y, text)
        y -= 6
        c.setStrokeColor(colors.grey)
        c.setLineWidth(1)
        c.line(30, y, width-30, y)
        y -= 18
        return y
    try:
        y = section_heading("WER Analysis Report", y, c, width, 18)
        c.setFont('Helvetica', 12)
        c.drawString(30, y, f"WER Score: {wer_results.get('wer_score', analysis.get('wer_score', 0.0)):.2%}")
        y -= 18
        c.drawString(30, y, f"Created: {analysis.get('created_at', '')}")
        y -= 24
    except Exception as e:
        print('PDF HEADER ERROR:', e)
        c.setFont('Helvetica', 12)
        c.drawString(30, y, "[Header not available]")
        y -= 20
    # File Metadata Section (like History page)
    try:
        meta = analysis.get('file_metadata') or analysis.get('metadata') or {}
        y = section_heading("File Information", y, c, width, 14)
        c.setFont('Helvetica', 11)
        file_info_lines = []
        file_info_lines.append(f"Filename: {meta.get('filename', 'Voice Recording')}")
        file_info_lines.append(f"Type: {meta.get('type', 'Unknown')}")
        size = meta.get('size')
        if size:
            if size < 1024:
                size_str = f"{size} bytes"
            elif size < 1024*1024:
                size_str = f"{size/1024:.1f} KB"
            else:
                size_str = f"{size/1024/1024:.2f} MB"
        else:
            size_str = 'N/A'
        file_info_lines.append(f"Size: {size_str}")
        created = meta.get('created')
        if created:
            from datetime import datetime
            try:
                created_str = datetime.fromisoformat(created).strftime('%m/%d/%Y, %I:%M:%S %p')
            except Exception:
                created_str = str(created)
        else:
            created_str = 'N/A'
        file_info_lines.append(f"{created_str}")
        for line in file_info_lines:
            c.drawString(40, y, line)
            y -= 14
        y -= 6
    except Exception as e:
        print('PDF FILE INFO ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(40, y, "[File information not available]")
        y -= 14
    # Transcribed Text
    try:
        y = section_heading("Transcribed Text", y, c, width, 14)
        c.setFont('Helvetica', 11)
        for line in split_text_to_lines(analysis.get('transcribed_text', ''), 90):
            c.drawString(40, y, line)
            y -= 14
            if y < 60:
                c.showPage(); y = height - 40
        y -= 16
    except Exception as e:
        print('PDF TRANSCRIBED TEXT ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(40, y, "[Transcribed text not available]")
        y -= 14
    # Reference Text
    try:
        y = section_heading("Reference Text", y, c, width, 14)
        c.setFont('Helvetica', 11)
        for line in split_text_to_lines(analysis.get('reference_text', ''), 90):
            c.drawString(40, y, line)
            y -= 14
            if y < 60:
                c.showPage(); y = height - 40
        y -= 16
    except Exception as e:
        print('PDF REFERENCE TEXT ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(40, y, "[Reference text not available]")
        y -= 14
    # Word Differences (use word_differences logic for counts)
    try:
        y = section_heading("Word Differences", y, c, width, 14)
        c.setFont('Helvetica', 11)
        word_diffs = wer_results.get('word_differences', analysis.get('word_differences', []))
        deletions = substitutions = insertions = 0
        i = 0
        while i < len(word_diffs):
            if word_diffs[i].get('type') == 'deleted' and i+1 < len(word_diffs) and word_diffs[i+1].get('type') == 'inserted':
                substitutions += 1
                i += 2
            elif word_diffs[i].get('type') == 'inserted':
                insertions += 1
                i += 1
            elif word_diffs[i].get('type') == 'deleted':
                deletions += 1
                i += 1
            elif word_diffs[i].get('type') == 'substituted':
                substitutions += 1
                i += 1
            else:
                i += 1
        c.setFont('Helvetica-Bold', 11)
        c.drawString(40, y, f"Deletions: ")
        c.setFont('Helvetica', 11)
        c.drawString(110, y, str(deletions))
        c.setFont('Helvetica-Bold', 11)
        c.drawString(180, y, f"Substitutions: ")
        c.setFont('Helvetica', 11)
        c.drawString(270, y, str(substitutions))
        c.setFont('Helvetica-Bold', 11)
        c.drawString(350, y, f"Insertions: ")
        c.setFont('Helvetica', 11)
        c.drawString(420, y, str(insertions))
        y -= 18
    except Exception as e:
        print('PDF WORD DIFFERENCES ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(40, y, "[Word differences not available]")
        y -= 14
    # Detailed Word Differences (as paragraph, with improved highlights)
    try:
        y = section_heading("Detailed Word Differences", y, c, width, 14)
        c.setFont('Helvetica', 11)
        word_diffs = wer_results.get('word_differences', analysis.get('word_differences', []))
        x = 40
        start_x = 40
        max_x = width - 40
        space_width = c.stringWidth(' ', 'Helvetica', 11)
        highlight_height = 12  # Reduced height
        highlight_offset = 2   # Offset to align with text baseline
        i = 0
        while i < len(word_diffs):
            diff = word_diffs[i]
            # Substitution: deleted followed by inserted (correction)
            if (diff.get('type') == 'deleted' and i+1 < len(word_diffs) and word_diffs[i+1].get('type') == 'inserted'):
                # Original (deleted, yellow background for substitution)
                word = diff['text']
                word_width = c.stringWidth(word, 'Helvetica', 11)
                c.setFillColorRGB(0.996, 0.953, 0.78)  # yellow
                c.setStrokeColorRGB(0.996, 0.953, 0.78)
                c.rect(x-2, y-highlight_offset, word_width+4, highlight_height, fill=1, stroke=0)
                c.setFillColorRGB(0.7, 0.27, 0.04)
                c.drawString(x, y, word)
                x += word_width + space_width
                # Correction (inserted, blue underline)
                corr = word_diffs[i+1]
                corr_word = corr['text']
                corr_width = c.stringWidth(corr_word, 'Helvetica', 11)
                c.setFillColorRGB(0.12, 0.25, 0.67)  # blue
                c.drawString(x, y, corr_word)
                # Draw underline
                underline_y = y-1
                underline_x = x
                underline_w = corr_width
                c.setStrokeColorRGB(0.12, 0.51, 0.96)
                c.setLineWidth(2)
                c.line(underline_x, underline_y, underline_x+underline_w, underline_y)
                x += corr_width + space_width
                i += 2
            elif diff.get('type') == 'substituted':
                word = diff['text']
                word_width = c.stringWidth(word, 'Helvetica', 11)
                c.setFillColorRGB(0.996, 0.953, 0.78)  # yellow
                c.setStrokeColorRGB(0.996, 0.953, 0.78)
                c.rect(x-2, y-highlight_offset, word_width+4, highlight_height, fill=1, stroke=0)
                c.setFillColorRGB(0.7, 0.27, 0.04)
                c.drawString(x, y, word)
                x += word_width + space_width
                i += 1
            elif diff.get('type') == 'inserted':
                word = diff['text']
                word_width = c.stringWidth(word, 'Helvetica-Oblique', 11)
                c.setFont('Helvetica-Oblique', 11)
                c.setFillColorRGB(0,0,0)
                c.drawString(x, y, word)
                # Draw strikethrough
                strike_y = y+2
                strike_x = x
                strike_w = word_width
                c.setStrokeColorRGB(0,0,0)
                c.setLineWidth(1)
                c.line(strike_x, strike_y, strike_x+strike_w, strike_y)
                x += word_width + space_width
                c.setFont('Helvetica', 11)
                i += 1
            elif diff.get('type') == 'deleted':
                word = diff['text']
                word_width = c.stringWidth(word, 'Helvetica', 11)
                c.setFillColorRGB(0.725, 0.11, 0.11)  # red
                c.setStrokeColorRGB(0.725, 0.11, 0.11)
                c.rect(x-2, y-highlight_offset, word_width+4, highlight_height, fill=1, stroke=0)
                c.setFillColorRGB(1,1,1)
                c.drawString(x, y, word)
                x += word_width + space_width
                i += 1
            else:
                word = diff['text']
                word_width = c.stringWidth(word, 'Helvetica', 11)
                c.setFillColorRGB(0,0,0)
                c.drawString(x, y, word)
                x += word_width + space_width
                i += 1
            # Wrap to next line if needed
            if x > max_x:
                x = start_x
                y -= 16
                if y < 60:
                    c.showPage(); y = height - 40
        y -= 18
    except Exception as e:
        print('PDF DETAILED WORD DIFFERENCES ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(40, y, "[Detailed word differences not available]")
        y -= 14
    # Edit Operations Table (horizontal, comma-separated, matching Detailed Word Differences logic, with wrapping)
    try:
        y = section_heading("Edit Operations Table", y, c, width, 14)
        word_diffs = wer_results.get('word_differences', analysis.get('word_differences', []))
        substituted, inserted, deleted = [], [], []
        i = 0
        while i < len(word_diffs):
            if word_diffs[i].get('type') == 'deleted' and i+1 < len(word_diffs) and word_diffs[i+1].get('type') == 'inserted':
                substituted.append(word_diffs[i]['text'])
                i += 2
            elif word_diffs[i].get('type') == 'inserted':
                inserted.append(word_diffs[i]['text'])
                i += 1
            elif word_diffs[i].get('type') == 'deleted':
                deleted.append(word_diffs[i]['text'])
                i += 1
            elif word_diffs[i].get('type') == 'substituted':
                substituted.append(word_diffs[i]['text'])
                i += 1
            else:
                i += 1
        c.setFont('Helvetica-Bold', 11)
        col_width = (width - 80) // 3
        col_xs = [40, 40 + col_width, 40 + 2*col_width]
        col_titles = ["Substituted:", "Inserted:", "Deleted:"]
        col_colors = [ (0.8, 0.6, 0), (0,0,0), (0.8, 0, 0) ]
        col_words = [substituted, inserted, deleted]
        # Draw headings
        for idx, (title, color) in enumerate(zip(col_titles, col_colors)):
            c.setFillColorRGB(*color)
            c.drawString(col_xs[idx], y, title)
        y -= 14
        c.setFont('Helvetica', 10)
        max_lines = 0
        # Draw words in columns, wrapping as needed
        for idx, (words, color) in enumerate(zip(col_words, col_colors)):
            c.setFillColorRGB(*color)
            x = col_xs[idx]
            line = ''
            line_y = y
            for w in words:
                w_str = w + ', '
                w_width = c.stringWidth(line + w_str, 'Helvetica', 10)
                if w_width > col_width - 10 and line:
                    c.drawString(x, line_y, line.rstrip(', '))
                    line_y -= 12
                    line = ''
                line += w_str
            if line:
                c.drawString(x, line_y, line.rstrip(', '))
                line_y -= 12
            if idx == 0:
                max_lines = max(max_lines, (y - line_y) // 12 + 1)
            else:
                max_lines = max(max_lines, (y - line_y) // 12 + 1)
        y -= max_lines * 12 + 6
    except Exception as e:
        print('PDF EDIT OPERATIONS TABLE ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(40, y, "[Edit operations table not available]")
        y -= 14
    # Statistics Table (black heading)
    try:
        stats = wer_results.get('statistics', analysis.get('statistics', {}))
        if stats:
            y = section_heading("Statistics", y, c, width, 14)
            c.setFillColorRGB(0,0,0)
            c.setFont('Helvetica-Bold', 11)
            c.drawString(40, y, "Metric"); c.drawString(180, y, "Transcribed"); c.drawString(320, y, "Reference")
            y -= 14
            c.setFont('Helvetica', 11)
            for metric, values in stats.items():
                c.drawString(40, y, str(metric))
                c.drawString(180, y, str(values.get('transcribed', '')))
                c.drawString(320, y, str(values.get('reference', '')))
                y -= 14
                if y < 60:
                    c.showPage(); y = height - 40
            y -= 10
    except Exception as e:
        print('PDF STATISTICS ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(40, y, "[Statistics not available]")
        y -= 14
    # NLP Results (black heading)
    try:
        if nlp_results:
            y = section_heading("NLP Analysis Results", y, c, width, 14)
            c.setFillColorRGB(0,0,0)
            for label, nlp in nlp_results.items():
                c.setFont('Helvetica-Bold', 12)
                c.drawString(40, y, f"{label.title()} Analysis:")
                y -= 14
                c.setFont('Helvetica', 10)
                for key, value in nlp.items():
                    c.setFont('Helvetica-Bold', 10)
                    c.drawString(50, y, f"{key.replace('_', ' ').title()}:")
                    y -= 12
                    c.setFont('Helvetica', 10)
                    if isinstance(value, list):
                        # Print horizontally with bullets, wrap as needed
                        line = ''
                        for v in value:
                            item = f"• {v} "
                            if len(line) + len(item) > 100:
                                c.drawString(65, y, line.strip())
                                y -= 11
                                if y < 60:
                                    c.showPage(); y = height - 40
                                line = ''
                            line += item
                        if line:
                            c.drawString(65, y, line.strip())
                            y -= 11
                            if y < 60:
                                c.showPage(); y = height - 40
                    else:
                        for line in split_text_to_lines(str(value), 90):
                            c.drawString(65, y, line)
                            y -= 11
                            if y < 60:
                                c.showPage(); y = height - 40
                    y -= 4
                y -= 8
    except Exception as e:
        print('PDF NLP RESULTS ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(40, y, "[NLP results not available]")
        y -= 14
    # Plots (high-res, avoid cutting off last graph)
    try:
        y = section_heading("Visualizations", y, c, width, 14)
        for plot_name in ['confusion_matrix', 'word_count_comparison', 'statistics_plot', 'radar_chart', 'linear_regression', 'bar_chart']:
            if plot_name in plots:
                try:
                    # Generate higher resolution image (scale=3)
                    img_bytes = pio.to_image(plots[plot_name], format='png', scale=3)
                    img = ImageReader(io.BytesIO(img_bytes))
                    # Check if enough space is left, else start new page
                    if y < 220:
                        c.showPage(); y = height - 40
                    # Center image
                    c.drawImage(img, width/2-125, y-180, width=250, height=150)
                    y -= 180
                    c.setFont('Helvetica-Oblique', 10)
                    c.drawCentredString(width/2, y-10, plot_name.replace('_', ' ').title())
                    y -= 30
                    if y < 100:
                        c.showPage(); y = height - 40
                except Exception as e:
                    print(f'PDF PLOT ERROR ({plot_name}):', e)
                    c.setFont('Helvetica', 11)
                    c.drawString(30, y, f"[{plot_name.replace('_', ' ').title()} not available]")
                    y -= 18
    except Exception as e:
        print('PDF VISUALIZATIONS ERROR:', e)
        c.setFont('Helvetica', 11)
        c.drawString(30, y, "[Visualizations not available]")
        y -= 14
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'wer_analysis_{id}.pdf', mimetype='application/pdf')

def split_text_to_lines(text, max_len):
    # Helper to split long text into lines for PDF
    import textwrap
    return textwrap.wrap(text, max_len)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 