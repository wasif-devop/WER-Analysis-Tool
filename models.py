from extensions import db
from datetime import datetime
import json

class Transcription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    transcribed_text = db.Column(db.Text)
    reference_text = db.Column(db.Text)
    wer_score = db.Column(db.Float)
    nlp_results = db.Column(db.Text)  # JSON string of NLP results
    analysis_results = db.Column(db.Text)  # JSON string of WER analysis results
    file_metadata = db.Column(db.Text)  # JSON string of file metadata

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'created_at': self.created_at.isoformat(),
            'transcribed_text': self.transcribed_text,
            'reference_text': self.reference_text,
            'wer_score': self.wer_score,
            'nlp_results': json.loads(self.nlp_results) if self.nlp_results else None,
            'analysis_results': json.loads(self.analysis_results) if self.analysis_results else None,
            'file_metadata': json.loads(self.file_metadata) if self.file_metadata else None
        } 