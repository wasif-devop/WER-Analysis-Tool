from weasyprint import HTML, CSS
from jinja2 import Template
import json
import os
from datetime import datetime
import plotly.io as pio
import base64
from io import BytesIO

class PDFGenerator:
    def __init__(self, template_dir: str):
        self.template_dir = template_dir
        self.css = CSS(string='''
            body { font-family: Arial, sans-serif; }
            .container { padding: 20px; }
            .header { text-align: center; margin-bottom: 30px; }
            .section { margin-bottom: 20px; }
            .section-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
            .text-box { border: 1px solid #ccc; padding: 10px; margin-bottom: 10px; }
            .stats { display: flex; justify-content: space-between; }
            .stat-item { text-align: center; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f5f5f5; }
            .plot { margin: 20px 0; }
            .footer { text-align: center; margin-top: 30px; font-size: 12px; }
        ''')

    def _convert_plot_to_base64(self, plot):
        """Convert Plotly figure to base64 string"""
        img_bytes = pio.to_image(plot, format='png')
        return base64.b64encode(img_bytes).decode()

    def _create_html_content(self, data: dict) -> str:
        """Create HTML content from analysis data"""
        template_str = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>WER Analysis Report</title>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Word Error Rate Analysis Report</h1>
                    <p>Generated on: {{ timestamp }}</p>
                </div>

                <div class="section">
                    <div class="section-title">File Information</div>
                    <table>
                        <tr>
                            <th>Filename</th>
                            <td>{{ metadata.filename }}</td>
                        </tr>
                        <tr>
                            <th>File Type</th>
                            <td>{{ metadata.extension }}</td>
                        </tr>
                        <tr>
                            <th>Size</th>
                            <td>{{ metadata.size }} bytes</td>
                        </tr>
                        <tr>
                            <th>Created</th>
                            <td>{{ metadata.created }}</td>
                        </tr>
                    </table>
                </div>

                <div class="section">
                    <div class="section-title">Text Comparison</div>
                    <div class="text-box">
                        <h3>Transcribed Text</h3>
                        <p>{{ transcribed_text }}</p>
                    </div>
                    <div class="text-box">
                        <h3>Reference Text</h3>
                        <p>{{ reference_text }}</p>
                    </div>
                </div>
                <div class="section">
                <div class="section-title">Edit Operations Table</div>
                <div style="display:flex;gap:16px;">
                    <div style="flex:1;">
                    <div style="background:#FEF3C7;color:#B45309;font-weight:bold;text-align:center;">Substituted</div>
                    <div style="background:#FEF9C3;color:#B45309;max-height:120px;overflow-y:auto;">
                        {% for w in substituted %}<div>{{ w }}</div>{% endfor %}
                    </div>
                    </div>
                    <div style="flex:1;">
                    <div style="background:#E5E7EB;color:#111827;font-weight:bold;text-align:center;">Inserted</div>
                    <div style="background:#F3F4F6;color:#111827;max-height:120px;overflow-y:auto;">
                        {% for w in inserted %}<div>{{ w }}</div>{% endfor %}
                    </div>
                    </div>
                    <div style="flex:1;">
                    <div style="background:#FEE2E2;color:#B91C1C;font-weight:bold;text-align:center;">Deleted</div>
                    <div style="background:#FECACA;color:#B91C1C;max-height:120px;overflow-y:auto;">
                        {% for w in deleted %}<div>{{ w }}</div>{% endfor %}
                    </div>
                    </div>
                </div>
                </div>
                <div class="section">
                    <div class="section-title">WER Analysis Results</div>
                    <div class="stats">
                        <div class="stat-item">
                            <h4>WER Score</h4>
                            <p>{{ "%.2f"|format(wer_score * 100) }}%</p>
                        </div>
                        <div class="stat-item">
                            <h4>Substitutions</h4>
                            <p>{{ differences.substitutions }}</p>
                        </div>
                        <div class="stat-item">
                            <h4>Deletions</h4>
                            <p>{{ differences.deletions }}</p>
                        </div>
                        <div class="stat-item">
                            <h4>Insertions</h4>
                            <p>{{ differences.insertions }}</p>
                        </div>
                    </div>
                </div>

                <div class="section">
                    <div class="section-title">Visualizations</div>
                    {% for plot_name, plot_data in plots.items() %}
                    <div class="plot">
                        <h3>{{ plot_name|title }}</h3>
                        <img src="data:image/png;base64,{{ plot_data }}" style="width: 100%;">
                    </div>
                    {% endfor %}
                </div>

                <div class="section">
                    <div class="section-title">NLP Analysis Results</div>
                    {% for nlp_type, nlp_data in nlp_results.items() %}
                    <div class="text-box">
                        <h3>{{ nlp_type|title }}</h3>
                        <pre>{{ nlp_data|tojson(indent=2) }}</pre>
                    </div>
                    {% endfor %}
                </div>

                <div class="footer">
                    <p>Developed by Wasif Ali</p>
                    <p>Instagram: <a href="https://www.instagram.com/waasu.devop">@waasu.devop</a></p>
                    <p>Behance: <a href="https://www.behance.net/wasifali51">wasifali51</a></p>
                </div>
            </div>
        </body>
        </html>
        '''

        template = Template(template_str)
        return template.render(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **data
        )

    def generate_pdf(self, data: dict, output_path: str):
        """Generate PDF report from analysis data"""
        # Convert plots to base64
        plots = {}
        for plot_name, plot in data['plots'].items():
            plots[plot_name] = self._convert_plot_to_base64(plot)

        # Create data dictionary for template
        template_data = {
            'metadata': data['metadata'],
            'transcribed_text': data['transcribed_text'],
            'reference_text': data['reference_text'],
            'wer_score': data['wer_score'],
            'differences': data['differences'],
            'plots': plots,
            'nlp_results': data['nlp_results']
        }

        # Generate HTML content
        html_content = self._create_html_content(template_data)

        # Generate PDF
        HTML(string=html_content).write_pdf(
            output_path,
            stylesheets=[self.css]
        ) 