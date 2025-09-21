from glob import glob
import chardet
import logging
from gpt_extract_step_cfgs import *
from RAG_database import RAGDatabase

logger = logging.getLogger('current_file_logger')
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s - %(filename)s - %(funcName)s] - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


class STEP:
    def __init__(self, step_text):
        self.step_text = step_text
        self.action, self.component, self.input, self.direction = self.step_parse()

    def step_parse(self):
        m = re.findall(r'\[(.*?)\]', self.step_text)
        if not self.is_step(m):
            print(f'Error: No actions found: {self.step_text}')
            return None, None, None, None

        action, component, input, direction = None, None, None, None

        if len(m) == 1:
            action = m[0]
            component = self.step_text.split(f"[{m[0]}]")[-1].strip()
        elif len(m) >= 2:
            action = m[0]
            component = m[1].strip()
            if len(m) > 2:
                input = m[2].strip() if 'input' in action.lower() else None
                direction = m[2].strip() if 'scroll' in action.lower() else None

        return action, component, input, direction

    def is_step(self, list_of_variable):
        return any(v.lower().replace('-', ' ') in ACTION_LISTS for v in list_of_variable)


class Extract_Steps:
    def __init__(self):
        self.chatgpt = ChatBot()

    def infer(self, question):
        response = self.chatgpt.chat(question)
        steps = []
        print(question)
        print(response)

        for line in response.split('\n'):
            line = line.strip()
            matches = re.findall(r'\[(.*?)\]', line)
            if matches:
                steps.append(line)

        valid_steps = []
        for step, line in enumerate(steps):
            line = line.strip()
            matches = re.findall(r'\[(.*?)\]', line)
            if matches:
                s = STEP(line.lstrip('0123456789. '))
                if s.action is None:
                    continue
                logger.info('\n{} \n  >>>> STEP-{}: [{}] [{}] [{}] [{}]'.format(
                    line, step, s.action, s.component, s.input, s.direction))
                valid_steps.append(s)

        steps_text = "\n".join([i.step_text for i in valid_steps])
        return response, steps_text.strip(), valid_steps

    def split_complex_step(self, text):
        parts = re.split(r'\s+and\s+|\s*,\s*|\s*while\s*|\s*then\s*', text)
        return [part.strip() for part in parts if part.strip()]

    def save_progress(self, progress_file, file_name):
        try:
            with open(progress_file, 'w', encoding='utf-8') as f:
                f.write(file_name)
        except Exception as e:
            print(f"An error occurred while saving progress: {e}")


def get_example(sentences, database, level):
    retrieved_results = {}
    if level == 'sentence':
        for sentence in sentences:
            sentence = sentence.strip()
            query_results_sentence1, query_results_analysis = database.search_similar(sentences, query=sentence,
                                                                                      level=level)
            if query_results_sentence1 is not None:
                query_results_sentence = re.sub(r'^\d+.\s*', '', query_results_sentence1)
                retrieved_results[query_results_sentence] = query_results_analysis
    elif level == 'report':
        report_content = '\n'.join(sentences)
        query_results_sentence1, query_results_analysis = database.search_similar(report_content, level)
        if query_results_sentence1 is not None and query_results_sentence1 not in retrieved_results:
            query_results_sentence = re.sub(r'^\d+.\s*', '', query_results_sentence1)
            retrieved_results[query_results_sentence] = query_results_analysis

    return retrieved_results


def report_to_steps(report_content, database, level):
    sentences = report_content.split('\n')
    retrieved_results = get_example(sentences, database, level)

    action_prompt = """Available actions: tap(click), input(set text), scroll, swipe, rotate, delete, double tap(click), long tap(click), restart, back]. """
    primitive_prompt = """Action primitives: [Tap] [Component], [Scroll] [Direction], [Input] [Component] [Value],[Rotate] [Component], [Delete] [Component] [Value], [Double-tap][Component], [Long-tap] [Component]."""
    example_prompt = f"The actions you identify should be in the available actions. Please extract the reproducing step entities from the bug report:\n"

    for example_sentence, example_labels in retrieved_results.items():
        label_str = ''
        for index, label in enumerate(example_labels):
            action = label['action'].lower()
            if 'input' in action:
                label_str += f"{index}. [Input] [{label['component']}] [{label['input']}]\n"
            elif 'scroll' in action:
                label_str += f"{index}. [Scroll] [{label['direction']}]\n"
            elif 'tap' in action:
                label_str += f"{index}. [Tap] [{label['component']}]\n"
            elif 'rotate' in action:
                label_str += f"{index}. [Rotate] [{label['direction']}]\n"
            elif 'delete' in action:
                label_str += f"{index}. [Delete] [{label['component']}] [{label['input']}]\n"
            elif 'double tap' in action:
                label_str += f"{index}. [Double-tap] [{label['component']}]\n"
            elif 'long tap' in action:
                label_str += f"{index}. [Long-tap] [{label['component']}]\n"
            if action not in ACTION_LISTS:
                logger.debug(f"Error: Invalid action found in example labels: {label}")
        label_str = label_str.strip()
        example_prompt += f"Report: \n{example_sentence}\nThe entities extracted from the report are: \n{label_str} \n"

    question_prompt = f'Please extract the reproducing step entities from the bug report:\nReport: \n'
    for sentence_id, report_sentence in enumerate(sentences):
        question_prompt += f"{sentence_id + 1}. {report_sentence}\n"

    format_prompt = f"Your response needs to follow the given order, like[action][component][direction][input] . Use [] as a placeholder for missing answers.The entities extracted from the report are:"
    prompt = f"{action_prompt}\n{primitive_prompt}\n{example_prompt}\n{question_prompt}\n{format_prompt}"

    es = Extract_Steps()
    response, steps_text, output = es.infer(prompt)
    return prompt, response, steps_text, output

def get_file_content(file_path):
    if not os.path.exists(file_path):
        return None

    with open(file_path, 'rb') as file:
        raw_data = file.read()
    encoding = chardet.detect(raw_data)['encoding']
    with open(file_path, 'r', encoding=encoding, errors='ignore') as file:
        return file.read().strip()



def process_files(report_dir, extract_output_base, database, progress_file):
    all_bug_reports = glob(os.path.join(report_dir, '*.txt'))

    for index, single_report_file in enumerate(all_bug_reports[0:151]):
        logger.info(f'processing {single_report_file}, {index} / {len(all_bug_reports)}')
        bug_id = os.path.basename(single_report_file).split('.')[0]
        report_content = get_file_content(single_report_file)
        progress_content = get_file_content(progress_file)

        if report_content in progress_content:
            continue

        prompt, response, steps_text, steps = report_to_steps(report_content, database, level='sentence')

        with open(progress_file, 'a', encoding='utf-8') as f:
            f.write(report_content + '\n')
            f.write('=' * 50 + '\n')
        save_dir = os.path.join(extract_output_base, 'extracted_steps')
        os.makedirs(save_dir, exist_ok=True)

        with open(os.path.join(save_dir, f'{bug_id}.txt'), 'w', encoding='utf-8') as fw:
            fw.write(prompt + '\n\n')
            fw.write('=' * 30 + '\n\n')
            fw.write(response + '\n\n')
            fw.write('=' * 30 + '\n\n')
            fw.write(steps_text + '\n')

        with open(progress_file, 'a', encoding='utf-8') as f:
            f.write(steps_text + '\n')
            f.write('=' * 50 + '\n')
        save_dir = os.path.join(extract_output_base, 'steps_only')
        os.makedirs(save_dir, exist_ok=True)

        with open(os.path.join(save_dir, f'{bug_id}.txt'), 'w', encoding='utf-8') as fw:
            fw.write(steps_text + '\n')



if __name__ == '__main__':
    report_dir = f'your_report_path'
    label_dir = f'your_label_path'
    preprocessed_label_path = f'reprocessed_label_path'
    processed_sentence_vector_path = f'preprocessed_label_path'
    processed_report_vector_path = f'processed_report_vector_path'

    database = RAGDatabase(processed_sentence_vector_path, processed_report_vector_path, preprocessed_label_path,
                           report_dir, label_dir)

    extract_output_base = f'extract_output_path'
    os.makedirs(extract_output_base, exist_ok=True)

    progress_file = os.path.join(extract_output_base, 'progress.txt')

    if not os.path.exists(progress_file):
        with open(progress_file, 'w') as f:
            f.write('')


    process_files(report_dir, extract_output_base, database, progress_file)


