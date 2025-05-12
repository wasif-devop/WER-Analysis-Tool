from werpy import wer
import numpy as np
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
from collections import Counter
import difflib

def flatten_and_split(s):
    if isinstance(s, str):
        return s.split()
    elif isinstance(s, list):
        flat = []
        for item in s:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)
        return flat
    else:
        return []

class WERCalculator:
    def __init__(self):
        pass

    def calculate_wer(self, reference: str, hypothesis: str) -> float:
        return wer(reference, hypothesis)

    def get_word_differences(self, reference: str, hypothesis: str):
        ref_words = reference.split()
        hyp_words = hypothesis.split()
        sm = difflib.SequenceMatcher(None, ref_words, hyp_words)
        differences = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                differences.append({'type': 'equal', 'ref': ref_words[i1:i2], 'hyp': hyp_words[j1:j2]})
            elif tag == 'replace':
                differences.append({'type': 'replace', 'ref': ref_words[i1:i2], 'hyp': hyp_words[j1:j2]})
            elif tag == 'delete':
                differences.append({'type': 'delete', 'ref': ref_words[i1:i2], 'hyp': []})
            elif tag == 'insert':
                differences.append({'type': 'insert', 'ref': [], 'hyp': hyp_words[j1:j2]})
        return differences

    def analyze_texts(self, reference: str, hypothesis: str):
        wer_score = self.calculate_wer(reference, hypothesis)
        differences = self.get_word_differences(reference, hypothesis)
        plots = {}
        for plot_name, plot_func in [
            ('confusion_matrix', self.generate_confusion_matrix),
            ('word_count_comparison', self.generate_word_count_comparison),
            ('statistics_plot', self.generate_statistics_plot),
            ('radar_chart', self.generate_radar_chart),
            ('linear_regression', self.generate_linear_regression_plot),
            ('bar_chart', self.generate_bar_chart)
        ]:
            try:
                fig = plot_func(reference, hypothesis)
                plots[plot_name] = fig
            except Exception as e:
                print(f"Failed to generate {plot_name}: {e}")
        return {
            'wer_score': wer_score,
            'differences': differences,
            'plots': plots
        }

    def generate_confusion_matrix(self, reference: str, hypothesis: str) -> go.Figure:
        ref_words = self.transformation(reference)
        hyp_words = self.transformation(hypothesis)
        
        # Create confusion matrix
        matrix = np.zeros((len(ref_words), len(hyp_words)))
        for i, ref_word in enumerate(ref_words):
            for j, hyp_word in enumerate(hyp_words):
                matrix[i, j] = 1 if ref_word == hyp_word else 0
        
        fig = go.Figure(data=go.Heatmap(
            z=matrix,
            x=hyp_words,
            y=ref_words,
            colorscale='Viridis'
        ))
        
        fig.update_layout(
            title='Word Confusion Matrix',
            xaxis_title='Hypothesis Words',
            yaxis_title='Reference Words',
            autosize=True,
            width=400,
            height=350,
            margin=dict(l=40, r=40, t=60, b=60)
        )
        
        return fig

    def generate_word_count_comparison(self, reference: str, hypothesis: str) -> go.Figure:
        ref_words = self.transformation(reference)
        hyp_words = self.transformation(hypothesis)
        
        ref_counts = Counter(ref_words)
        hyp_counts = Counter(hyp_words)
        
        all_words = sorted(set(ref_words) | set(hyp_words))
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Reference',
            x=all_words,
            y=[ref_counts.get(word, 0) for word in all_words]
        ))
        fig.add_trace(go.Bar(
            name='Hypothesis',
            x=all_words,
            y=[hyp_counts.get(word, 0) for word in all_words]
        ))
        
        fig.update_layout(
            title='Word Count Comparison',
            xaxis_title='Words',
            yaxis_title='Count',
            barmode='group',
            autosize=True,
            width=400,
            height=350,
            margin=dict(l=40, r=40, t=60, b=100),
            xaxis_tickangle=-45
        )
        
        return fig

    def generate_statistics_plot(self, reference: str, hypothesis: str) -> go.Figure:
        ref_words = self.transformation(reference)
        hyp_words = self.transformation(hypothesis)
        
        ref_lengths = [len(word) for word in ref_words]
        hyp_lengths = [len(word) for word in hyp_words]
        
        fig = go.Figure()
        
        # Add box plots for word lengths
        fig.add_trace(go.Box(
            y=ref_lengths,
            name='Reference',
            boxpoints='all'
        ))
        fig.add_trace(go.Box(
            y=hyp_lengths,
            name='Hypothesis',
            boxpoints='all'
        ))
        
        fig.update_layout(
            title='Word Length Statistics',
            yaxis_title='Word Length',
            showlegend=True,
            autosize=True,
            width=400,
            height=350,
            margin=dict(l=40, r=40, t=60, b=60)
        )
        
        return fig

    def generate_radar_chart(self, reference: str, hypothesis: str) -> go.Figure:
        ref_words = self.transformation(reference)
        hyp_words = self.transformation(hypothesis)
        metrics = ['Word Count', 'Unique Words', 'Avg Word Length']
        ref_vals = [len(ref_words), len(set(ref_words)), np.mean([len(w) for w in ref_words]) if ref_words else 0]
        hyp_vals = [len(hyp_words), len(set(hyp_words)), np.mean([len(w) for w in hyp_words]) if hyp_words else 0]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=ref_vals + [ref_vals[0]], theta=metrics + [metrics[0]], fill='toself', name='Reference'))
        fig.add_trace(go.Scatterpolar(r=hyp_vals + [hyp_vals[0]], theta=metrics + [metrics[0]], fill='toself', name='Hypothesis'))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True)),
            showlegend=True,
            title='Text Metrics Radar Chart',
            autosize=True,
            width=400,
            height=350,
            margin=dict(l=40, r=40, t=60, b=60)
        )
        return fig

    def generate_linear_regression_plot(self, reference: str, hypothesis: str) -> go.Figure:
        ref_words = self.transformation(reference)
        hyp_words = self.transformation(hypothesis)
        # Use word positions as x, word lengths as y
        x_ref = list(range(len(ref_words)))
        y_ref = [len(w) for w in ref_words]
        x_hyp = list(range(len(hyp_words)))
        y_hyp = [len(w) for w in hyp_words]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x_ref, y=y_ref, mode='markers+lines', name='Reference'))
        fig.add_trace(go.Scatter(x=x_hyp, y=y_hyp, mode='markers+lines', name='Hypothesis'))
        fig.update_layout(
            title='Word Length Linear Regression',
            xaxis_title='Word Position',
            yaxis_title='Word Length',
            autosize=True,
            width=400,
            height=350,
            margin=dict(l=40, r=40, t=60, b=60)
        )
        return fig

    def generate_bar_chart(self, reference: str, hypothesis: str) -> go.Figure:
        # Compare deletions, substitutions, insertions (dummy values for now)
        ref_words = self.transformation(reference)
        hyp_words = self.transformation(hypothesis)
        sm = difflib.SequenceMatcher(None, ref_words, hyp_words)
        deletions = substitutions = insertions = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'replace':
                substitutions += max(i2 - i1, j2 - j1)
            elif tag == 'delete':
                deletions += i2 - i1
            elif tag == 'insert':
                insertions += j2 - j1
        fig = go.Figure([go.Bar(x=['Deletions', 'Substitutions', 'Insertions'], y=[deletions, substitutions, insertions])])
        fig.update_layout(
            title='Edit Operations Bar Chart',
            yaxis_title='Count',
            autosize=True,
            width=400,
            height=350,
            margin=dict(l=40, r=40, t=60, b=60),
            xaxis_tickangle=-30
        )
        return fig

    def transformation(self, text: str):
        return text.split() 