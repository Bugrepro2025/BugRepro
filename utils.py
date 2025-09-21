import re
import os
import ast
import json
from handle_command import *
import subprocess
import base64
import chardet


def clear_logcat(device_port):
    adb_command = ['adb', '-s', device_port, 'logcat', '-c']
    subprocess.run(adb_command)




def get_logcat(device_port):
    adb_command = ['adb', '-s', device_port, 'logcat', '-d', '*:E']
    try:
        result = subprocess.run(adb_command, capture_output=True, text=True, timeout=2)
    except subprocess.TimeoutExpired:
        print("Get logcat did not complete within the timeout period.")
        return ''
    if result.returncode != 0:  
        raise Exception("adb logcat failed, make sure your device is connected and adb is installed")
    return result.stdout  


def read_bug_report(file_path, bug_app_info):
    def try_decode(content, encodings):
        for encoding in encodings:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode('utf-8', errors='replace')

    with open(file_path, 'rb') as f:
        content = f.read()

        detected_encoding = chardet.detect(content)['encoding']
        if detected_encoding:
            try:
                single_report = content.decode(detected_encoding)
            except UnicodeDecodeError:
                encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'ascii', 'iso-8859-1']
                single_report = try_decode(content, encodings)
        else:
            encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'ascii', 'iso-8859-1']
            single_report = try_decode(content, encodings)

    bug_report = ' '.join([line.strip() for line in single_report.splitlines() if line.strip()])
    return f"App Name: {bug_app_info['package_name']}. Bug Report: {bug_report}"


def load_training_prompts(path):
    with open(path, 'r',encoding='utf-8') as f:
        return json.load(f)


def convert_message_to_command_list(message):
    try:
        if "[" in message and "]" in message:
            start_index = message.index("[")
            end_index = message.rindex("]")
            message = message[start_index:end_index + 1]
            if message == "[]" or message == "[{}]":
                command_list = []
            else:
                command_list = ast.literal_eval(message)
        elif "{" in message and "}" in message:
            start_index = message.index("{")
            end_index = message.rindex("}")
            message = message[start_index:end_index + 1]
            if message == "{}":
                command_list = []
            else:
                command_list = [ast.literal_eval(message)]
        else:
            command_list = []
        return command_list
    except (ValueError, SyntaxError) as e:
        print(f"Unable to convert message to command list: {str(e)}")
        return []


def add_commands(commands, new_commands):
    if new_commands is None:
        return None
    commands.extend(new_commands)
    sequence = has_repeating_sequence(commands)
    if sequence:
        return f"Repeating sequence detected: , {sequence}"
    return None


def has_repeating_sequence(commands):
    length = len(commands)
    for seq_length in range(1, length // 2 + 1):
        sequence = commands[length - 2 * seq_length: length - seq_length]
        next_sequence = commands[length - seq_length:]
        if sequence == next_sequence:
            return sequence
    return None


def count_command_and_response(execution_data, command_list):

    try:
        if command_list is not None and len(command_list) > 0:
            execution_data[2] += len(command_list)
    except Exception as e:
        print(f"Error in count_command_and_response: {e}")