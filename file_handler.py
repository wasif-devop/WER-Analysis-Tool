import os
import speech_recognition as sr
from PIL import Image
import pytesseract
import PyPDF2
from docx import Document
import json
from typing import Dict, Optional
import wave
import contextlib
import numpy as np
import whisper

class FileHandler:
    def __init__(self, upload_folder: str):
        self.upload_folder = upload_folder
        self.recognizer = sr.Recognizer()
        self.supported_audio = {'.mp3', '.wav'}
        self.supported_video = {'.mp4', '.mkv'}
        self.supported_text = {'.txt', '.pdf', '.docx'}
        self.supported_image = {'.png', '.jpg', '.jpeg'}

    def get_file_metadata(self, file_path: str) -> Dict:
        """Extract metadata from file"""
        file_stats = os.stat(file_path)
        _, ext = os.path.splitext(file_path)
        
        metadata = {
            'filename': os.path.basename(file_path),
            'extension': ext,
            'size': file_stats.st_size,
            'created': file_stats.st_ctime,
            'modified': file_stats.st_mtime
        }
        
        # Add duration for audio/video files
        if ext in self.supported_audio | self.supported_video:
            try:
                with contextlib.closing(wave.open(file_path, 'r')) as f:
                    frames = f.getnframes()
                    rate = f.getframerate()
                    duration = frames / float(rate)
                    metadata['duration'] = duration
            except:
                metadata['duration'] = None
        
        return metadata

    def extract_text_from_audio(self, file_path: str) -> str:
        """Extract text from audio file using OpenAI Whisper"""
        try:
            model = whisper.load_model("base")  # You can use 'tiny', 'small', etc. for speed/accuracy tradeoff
            result = model.transcribe(file_path)
            return result['text']
        except Exception as e:
            return f"Whisper transcription error: {str(e)}"

    def extract_text_from_image(self, file_path: str) -> str:
        """Extract text from image using OCR"""
        try:
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image)
            return text
        except Exception as e:
            return f"Error extracting text from image: {str(e)}"

    def extract_text_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF file"""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
        except Exception as e:
            return f"Error extracting text from PDF: {str(e)}"

    def extract_text_from_docx(self, file_path: str) -> str:
        """Extract text from DOCX file"""
        try:
            doc = Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text
        except Exception as e:
            return f"Error extracting text from DOCX: {str(e)}"

    def extract_audio_from_video(self, file_path: str, out_wav_path: str, max_duration_sec: int = 60) -> bool:
        """Extract the first max_duration_sec seconds of audio from a video file using ffmpeg."""
        import subprocess
        try:
            cmd = [
                'ffmpeg', '-y', '-i', file_path,
                '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                '-t', str(max_duration_sec), out_wav_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except Exception as e:
            print(f"Error extracting audio from video: {e}")
            return False

    def process_file(self, file_path: str) -> Dict:
        """Process file and extract text based on file type, with video/image support and limits."""
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        text = ""
        max_size = 100 * 1024 * 1024  # 100MB
        if os.path.getsize(file_path) > max_size:
            return {'text': '', 'error': 'File too large. Maximum allowed size is 100MB.'}
        if ext in self.supported_audio:
            text = self.extract_text_from_audio(file_path)
        elif ext in self.supported_video:
            # Extract audio from video, trim to 1 minute
            out_wav = file_path + '_audio.wav'
            ok = self.extract_audio_from_video(file_path, out_wav, max_duration_sec=60)
            if not ok:
                return {'text': '', 'error': 'Failed to extract audio from video.'}
            text = self.extract_text_from_audio(out_wav)
            os.remove(out_wav)
        elif ext in self.supported_image:
            try:
                text = self.extract_text_from_image(file_path)
            except Exception as e:
                return {'text': '', 'error': f'Image OCR failed: {str(e)}'}
        elif ext == '.pdf':
            text = self.extract_text_from_pdf(file_path)
        elif ext == '.docx':
            text = self.extract_text_from_docx(file_path)
        elif ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
        else:
            return {'text': '', 'error': 'Unsupported file type.'}
        metadata = self.get_file_metadata(file_path)
        return {'text': text, 'metadata': metadata}

    def save_file(self, file, filename: str) -> Optional[str]:
        """Save uploaded file and return the path"""
        try:
            file_path = os.path.join(self.upload_folder, filename)
            file.save(file_path)
            return file_path
        except Exception as e:
            print(f"Error saving file: {str(e)}")
            return None 