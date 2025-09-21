This the implementation of our paper **BugRepro: Enhancing Android Bug Reproduction
with Domain-Specific Knowledge Integration**.

## Introduction
We proposed BugRepro in this paper for more accurate android bug reproduction. BugRepro retrieves similar bug reports along with their corresponding S2R entities from an example-rich RAG document. This document serves as a valuable reference for improving the accuracy of S2R entity extraction.
In addition, BugRepro incorporates app-specific knowledge. It explores the app’s graphical user interface (GUI) and extracts UI transition graphs. These graphs are used to guide large language models (LLMs) in their exploration process when they encounter bottlenecks. Our experiments demonstrate the effectiveness of BugRepro. Our method significantly outperforms two state-of-the-art methods.  For S2R entity extraction accuracy, it achieves a 7.57 to 28.89 percentage point increase over prior methods. For the bug reproduction success rate, the improvement reaches 74.55% and 152.63%. In reproduction efficiency, the gains are 0.72% and 76.68%.



## Getting Started

### Structure of the code

```
bug_validation.py    -- verify whether a bug is triggered
execution.py         -- interact with andorid simulators
extract_steps.py     -- extract S2Rs from bug reports
get_element_tree.py  -- get the element tree from a android page
ui_exploration.py      -- parse android layouts and UI elements
RAG_database.py      -- constructs the RAG database used in BugRepro
replay_main.py.      -- main function for bug reproduction
utils.py             -- some tool functions
```



### Extract S2Rs

In `extract_steps.py`, set the paths to your real data paths from line 201-205

```
report_dir = f'your_report_path'
label_dir = f'your_label_path'
preprocessed_label_path = f'reprocessed_label_path'
processed_sentence_vector_path = f'preprocessed_label_path'
processed_report_vector_path = f'processed_report_vector_path'
```

Set the output path in line 210

```
extract_output_base = f'extract_output_path'
```

Then execute

```
python extract_steps.py
```

The execution progress will be stored in `progress.txt`, and the output will be stored in previously set `extract_output_base`



### Replay

From line 421 to 424, set the necessary informations.

```
device_id_port = "your_device_id_port"
report_path = "path/to/single_report.txt"
apk_file_path = "path/to/apk_info.json"
output_file = "path/to/result.json"
```

We leveraged Genymotion emulators as the android device used in our experiments.

Then execute `python replay_main.py` and the results will be saved at `output_file`.


## Acknowledgments

Our implementation utilizes a portion of the code from the ReBL project. We thank its authors for making their work available. **([https://github.com/original-author/data-parser](https://github.com/datareviewtest/ReBL/blob/main/Automation/prompts/.DS_Store))**
