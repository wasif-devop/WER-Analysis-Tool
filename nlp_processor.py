import nltk
import spacy
from nltk.stem import PorterStemmer, WordNetLemmatizer
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.corpus import wordnet
import re

# Download required NLTK data
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')

# Load spaCy model
nlp = spacy.load('en_core_web_sm')

class NLPProcessor:
    def __init__(self):
        self.stemmer = PorterStemmer()
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))

    def normalize_text(self, text):
        # Convert to lowercase and remove extra whitespace
        text = text.lower().strip()
        # Remove special characters and digits
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        return text

    def tokenize(self, text):
        return word_tokenize(text)

    def remove_stopwords(self, tokens):
        return [token for token in tokens if token not in self.stop_words]

    def stem_words(self, tokens):
        return [self.stemmer.stem(token) for token in tokens]

    def lemmatize_words(self, tokens):
        return [self.lemmatizer.lemmatize(token) for token in tokens]

    def get_pos_tags(self, text):
        doc = nlp(text)
        return [(token.text, token.pos_) for token in doc]

    def get_named_entities(self, text):
        doc = nlp(text)
        return [(ent.text, ent.label_) for ent in doc.ents]

    def expand_synonyms(self, tokens):
        synonyms = []
        for token in tokens:
            synsets = wordnet.synsets(token)
            if synsets:
                # Get synonyms from the first synset
                synset = synsets[0]
                synonyms.extend([lemma.name() for lemma in synset.lemmas()])
        return list(set(synonyms))

    def process_text(self, text):
        normalized = self.normalize_text(text)
        tokens = self.tokenize(normalized)
        tokens_no_stop = self.remove_stopwords(tokens)
        
        return {
            'normalized_text': normalized,
            'tokenized_words': tokens,
            'tokens_without_stopwords': tokens_no_stop,
            'stemmed_words': self.stem_words(tokens),
            'lemmatized_words': self.lemmatize_words(tokens),
            'pos_tags': self.get_pos_tags(text),
            'named_entities': self.get_named_entities(text),
            'synonyms': self.expand_synonyms(tokens)
        } 