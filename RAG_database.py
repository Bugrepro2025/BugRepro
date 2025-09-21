import os
import json
import chardet
import numpy as np
from glob import glob
from typing import List
from collections import defaultdict
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger('current_file_logger')
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s - %(filename)s - %(funcName)s] - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


def get_file_content(file_path):
    if not os.path.exists(file_path):
        return None

    with open(file_path, 'rb') as file:
        raw_data = file.read()
    encoding = chardet.detect(raw_data)['encoding']
    with open(file_path, 'r', encoding=encoding, errors='ignore') as file:
        return file.read().strip()


class RAGDatabase:
    def __init__(self, processed_sentence_vector_path, processed_report_vector_path, preprocessed_label_path,
                 raw_reports_dir, raw_labels_dir) -> None:

        self.raw_reports_dir = raw_reports_dir
        self.raw_labels_dir = raw_labels_dir

        if not os.path.exists(processed_sentence_vector_path):
            self.preprocess_reports_sentence_vector(raw_reports_dir, processed_sentence_vector_path)

        if not os.path.exists(processed_report_vector_path):
            self.process_report_vector(raw_reports_dir, processed_report_vector_path)

        if not os.path.exists(preprocessed_label_path):
            self.preprocess_reports_label(raw_labels_dir, preprocessed_label_path)

        self.processed_sentence_vector = dict(json.load(open(processed_sentence_vector_path, 'r', encoding='utf-8')))
        self.processed_report_vector = dict(json.load(open(processed_report_vector_path, 'r', encoding='utf-8')))
        self.processed_label = dict(json.load(open(preprocessed_label_path, 'r', encoding='utf-8')))

    def collect_sentences(self, raw_reports_dir):
        sentences = []
        all_reports = glob(os.path.join(raw_reports_dir, '*.txt'))
        for single_report_file in all_reports:
            report_content = get_file_content(single_report_file)
            sentences.extend(report_content.split('\n'))
        return sentences

    def preprocess_reports_sentence_vector(self, raw_reports_dir, processed_sentence_vector_path):
        logger.debug('Embedding reports sentences')
        all_sentences = self.collect_sentences(raw_reports_dir)
        processed_vector = defaultdict()
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L12-v2')
        embeddings = model.encode(all_sentences)

        for embedding, sentence in zip(embeddings, all_sentences):
            processed_vector[sentence] = embedding.tolist()

        with open(processed_sentence_vector_path, 'w', encoding='utf-8') as f:
            json.dump(processed_vector, f, ensure_ascii=False)
        logger.debug('Embedding reports sentences done')

    def process_report_vector(self, raw_reports_dir, processed_report_vector_path):
        processed_vector = defaultdict()
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L12-v2')

        all_report_contents = []
        all_reports = glob(os.path.join(raw_reports_dir, '*.txt'))
        for single_report_file in all_reports:
            report_content = get_file_content(single_report_file)
            all_report_contents.append(report_content)
        report_embeddings = model.encode(all_report_contents)

        for embedding, report_content in zip(report_embeddings, all_report_contents):
            processed_vector[report_content] = embedding.tolist()

        with open(processed_report_vector_path, 'w', encoding='utf-8') as f:
            json.dump(processed_vector, f, ensure_ascii=False)
        logger.debug('Embedding reports done')

    def preprocess_reports_label(self, raw_reports_dir, preprocessed_label_path):
        logger.debug('Preprocessing reports labels')
        all_label_files = glob(os.path.join(raw_reports_dir, '*.csv'))
        sentence_label_dict = defaultdict(list)

        for single_label_file in all_label_files:
            label_content = get_file_content(single_label_file)

            for line in label_content.split('\n'):
                if 'Component' in line and 'Action' in line:
                    continue
                sentence = line.split(',')[1]
                action = line.split(',')[3]
                component = line.split(',')[4]
                input_value = line.split(',')[5]
                direction = line.split(',')[6]

                if sentence not in sentence_label_dict:
                    sentence_label_dict[sentence] = []

                sentence_label_dict[sentence].append({
                    'action': action,
                    'component': component,
                    'input': input_value,
                    'direction': direction
                })

        with open(preprocessed_label_path, 'w', encoding='utf-8') as f:
            json.dump(sentence_label_dict, f, ensure_ascii=False, indent=4)
        logger.debug('Preprocessing reports labels done')
        pass

    def get_similarity(self, vector1: List[float], vector2: List[float]) -> float:
        dot_product = np.dot(vector1, vector2)
        magnitude = np.linalg.norm(vector1) * np.linalg.norm(vector2)
        if not magnitude:
            return 0
        return dot_product / magnitude

    def search_similar(self, sentences, query: str, level="sentence"):
        if level == 'report':
            vector_base = self.processed_report_vector
        else:
            vector_base = self.processed_sentence_vector
        try:
            query_vector = vector_base[query]
        except KeyError:
            model = SentenceTransformer('sentence-transformers/all-MiniLM-L12-v2')
            query_vector = model.encode([query])

        similarity_dict = {}
        for sentence, vector in vector_base.items():
            if sentence == query:
                continue
            if sentence in sentences:
                continue
            similarity = self.get_similarity(query_vector, vector)
            similarity_dict[sentence] = similarity

        sorted_similarity = sorted(similarity_dict.items(), key=lambda x: x[1], reverse=True)
        count = 0
        max_checks = len(sentences) + 3
        # Get the most similar sentence
        for single_sentence, similarity in sorted_similarity[:max_checks]:
            target_label = self.processed_label.get(single_sentence)
            if not target_label or target_label == [{'action': '', 'component': '', 'direction': '', 'input': ''}]:
                count += 1
                if count == max_checks:
                    return None, None
                continue
            available = all(i['action'] and 'No content found' not in i['action'] for i in target_label)
            if available:
                return single_sentence, target_label
        return None, None


if __name__ == '__main__':
    pass