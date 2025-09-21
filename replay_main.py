from utils import *
from bug_validation import *
from  gpt_replay_cfgs import *
from handle_command import *
import logging
from func_timeout import func_set_timeout, FunctionTimedOut
import json
import chardet
from ui_exploration import get_screen_information
import os
import subprocess
import time
import uiautomator2 as u2
from datetime import datetime
from collections import defaultdict

timeout_value = 300



def install_and_launch_app(apk_file_path, bug_app_info, logger, report_file_name, max_attempts=5):
    adb_command = ['adb', 'install', apk_file_path]
    subprocess.run(adb_command, cwd=os.getcwd())
    logger.info('Successfully install the app')
    d = u2.connect()
    for attempt in range(max_attempts):
        try:
            d.app_start(bug_app_info['package_name'],
                        activity=bug_app_info['activity'],
                        )
            time.sleep(2)
            if d.app_current()['package'] == bug_app_info['package_name']:
                logger.info(f'Successfully launch the app on attempt {attempt + 1}')
                return True
            else:
                d.app_start(bug_app_info['package_name'])
                time.sleep(2)
                current_activity = d.app_current()['activity'].lower()
                if 'welcome' in current_activity:
                    logger.info("current activity is welcome")
                if 'permission' in current_activity:
                    logger.info("current activity is permission")
                logger.info(f'Successfully start the app on attempt {attempt + 1}')
                return True
        except Exception as e:
            logger.error(f'Launch attempt {attempt + 1} failed: {str(e)}')
    with open(output_file, 'a+') as fw:
        fw.write(json.dumps({
            "report_file_name": report_file_name,
            'error': "Failed to launch the app for 5 times"
        }) + '\n')
    logger.info('Failed to launch the app for 5 times')
    return False


def uninstall_app(bug_app_info, logger):
    adb_command = ['adb', 'uninstall', bug_app_info['package_name']]
    subprocess.run(adb_command)
    logger.info('Successfully uninstall the app')



def get_extracted_steps(step_file):
    try:
        with open(step_file, 'rb') as f:
            rawdata = f.read()
        result = chardet.detect(rawdata)
        charenc = result['encoding'] or 'utf-8' or 'gbk' or 'gb2312' or 'iso-8859-1' or 'ascii'  # 如果检测失败则默认使用utf-8

        try:
            return rawdata.decode(charenc).splitlines()
        except UnicodeDecodeError:
            for encoding in ['utf-8', 'gbk', 'iso-8859-1']:
                try:
                    return rawdata.decode(encoding).splitlines()
                except UnicodeDecodeError:
                    continue
            return rawdata.decode('utf-8', errors='ignore').splitlines()
    except Exception as e:
        print('Error in get_extracted_steps:', e)
        return None


def get_prompt(device, attribute_to_element_map, package_name, execution_status, flags, need_ui_explore, emulator_id,logger):
    bug_report, need_hint, repeating_commands = flags
    widget_dict_1, info_1, recovery_succeed, clickable_count_1 = get_screen_information(device,
                                                                                        attribute_to_element_map,
                                                                                        package_name,
                                                                                        emulator_id, False)
    attribute_to_element_map_2 = defaultdict(list)
    widget_dict_2, info_2, recovery_succeed, clickable_count_2 = get_screen_information(device,
                                                                                        attribute_to_element_map_2,
                                                                                        package_name,
                                                                                        emulator_id, False)

    if widget_dict_1 == widget_dict_2:
        info = info_2
        attribute_to_element_map = attribute_to_element_map_2
        clickable_count = clickable_count_2
    else:
        info = f"There are a UI quickly disappear(less than 0.5s) after {execution_status}. The UI information of the page is {{info_1}}. If the next action related to the quick diappear page, Please provide a seris of actions to tigger the quick disappear UI then execute actions on the relevant transient widget in one go. Current page is {info_2}.  It the quick diappear UI is not related, we can ignore it and proceeed based on the state of current page"
        clickable_count = clickable_count_2

    if need_hint:
        hint = "Your suggestion is None."
        if need_ui_explore:
            widget_dict_2, info, recovery_succeed, clickable_count = get_screen_information(device,
                                                                                            attribute_to_element_map_2,
                                                                                            package_name, emulator_id,
                                                                                            True)
        if logger:
            logger.info(f"UI Exploration - Total clickable elements processed: {clickable_count}")
        prompt = f"{hint}. {info}"
        flags[1] = False
    elif repeating_commands:
        warning = f"Just a reminder, we are repeating the following steps {repeating_commands}. If the bug report doesn't require repeated steps, it seems like we're trapped into a loop. If you believe we are in the right track, maybe try different text for set_text. If there are more other widgets, maybe try a different path"
        prompt = f"{warning}. {info}"
        flags[2] = None
    else:
        prompt = f"{execution_status}.{info}"

    return widget_dict_2, prompt, recovery_succeed


def execute_commands(command_list, device, widget_dict, attribute_to_element_map, package_name):

    if not command_list:
        return ["No commands to execute"]

    execution_status = []

    for i, command in enumerate(command_list):
        try:
            if not isinstance(command, dict):
                execution_status.append(f"Command {i + 1} is not a valid dict: {command}")
                continue

            if 'action' not in command:
                execution_status.append(f"Command {i + 1} missing 'action' field: {command}")
                continue

            print(f"Executing command {i + 1}: {command}")
            status = handle_command(command, device, attribute_to_element_map, package_name)

            if status == True:
                if command['action'] in ['swipe']:
                    execution_status.append(
                        f"Successfully execute {command} but please make sure you swipe to the correct location, if not either keep swiping or change the from_direction and to_direction. And keep in mind that swiping between multi-page layout, one swipe is just going to the next layout")
                else:
                    execution_status.append(f"Successfully execute {command}")
            elif status == False:
                execution_status.append(f"Failed to execute {command}")
            else:
                execution_status.append(status)

        except Exception as e:
            execution_status.append(f"Failed to execute command {i + 1} {command}. Error message: {e}")

        time.sleep(1)

    return execution_status


@func_set_timeout(timeout_value)
def reproduce_bug(device_port, reprot_file_name, bug_app_info, extracted_steps, need_ui_explore, logger):
    device = u2.connect(device_port)
    clear_logcat(device_port)

    device.set_orientation("natural")
    package_name = device.app_current()['package']
    bug_report = read_bug_report(reprot_file_name, bug_app_info)

    history = load_training_prompts('./prompts/training_prompts_ori.json')
    history.append({"role": "user", "content": f"{bug_report}"})
    history.append({"role": "user", "content": f"The extracted steps to reproduce the bug is {extracted_steps}"})

    execution_data = [dt.now(), 0, 0]
    flags = [None, False, False, None]
    crash = False
    widget_dict, other_text, prompt = None, None, None
    executed_commands, execution_status = [], []
    last_executed_action = None  

    logger.info('Basic setup finished.')

    while not crash:
        attribute_to_element_map = defaultdict(list)
        widget_dict, prompt, recovery_succeed = get_prompt(device, attribute_to_element_map, package_name,
                                                           execution_status, flags, need_ui_explore, device_port,logger)
        if not recovery_succeed:
            logger.info('Recovery failed, need reboot!')
            return False

        print(f"*Prompt: {prompt}")
        logger.info(f"*Prompt: {prompt}")
        response, history = generate_text(prompt, history, package_name)
        message = get_message(response)

        print('###############################################\n')
        logger.info('###############################################\n')
        print(f"*GPT message: {message}")
        logger.info(f"*GPT message: {message}")
        print('\n###############################################')
        logger.info('\n###############################################')

        try:
            command_list = convert_message_to_command_list(message)
            print(f"*Converted commands: {command_list}")
            logger.info(f"*Converted commands: {command_list}")

            if command_list is not None:
                if not isinstance(command_list, list):
                    print(f"*Warning: command_list is not a list: {type(command_list)}, setting to None")
                    logger.info(f"*Warning: command_list is not a list: {type(command_list)}, setting to None")
                    command_list = None
                elif len(command_list) == 0:
                    print("*Warning: command_list is empty, setting to None")
                    logger.info("*Warning: command_list is empty, setting to None")
                    command_list = None
                else:
                    valid = True
                    for i, cmd in enumerate(command_list):
                        if not isinstance(cmd, dict):
                            valid = False
                            break
                        elif 'action' not in cmd and 'result' not in cmd:
                            valid = False
                            break

                    if not valid:
                        command_list = None

        except Exception as e:
            print(f"*Command conversion error: {e}")
            logger.info(f"*Command conversion error: {e}")
            command_list = None

        try:
            count_command_and_response(execution_data, command_list)
        except Exception as e:
            print(f"*Command counting error: {e}")
            logger.info(f"*Command counting error: {e}")

        history.append({"role": "assistant", "content": message})

        if command_list is None or command_list == []:
            logger.info("*No valid commands found, setting need_hint=True")
            flags[1] = True  
            device.set_orientation("natural")
            time.sleep(0.8)
        elif len(command_list) > 0 and command_list[0].get('result', None) is not None:
            result_value = command_list[0].get('result')
            logger.info(f"*Result detected: {result_value}")

            if result_value == "success" or result_value == True:
                logger.info("*Bug reproduction successful!")
                crash = True
            else:
                logger.info("*Bug reproduction failed, setting need_hint=True")
                flags[1] = True
        elif len(command_list) > 0 and command_list[0].get('action', '') == 'check crash':
            logger.info("*Check crash command detected")
            crash = check_crash()
            if not crash:
                time.sleep(0.5)
                crash = check_error_keywords(get_current_hierarchy(device), package_name) \
                        or 'crashreport' in device.app_current()['activity'].lower()
                
        else:
            print(f"*Executing {len(command_list)} commands")
            logger.info(f"*Executing {len(command_list)} commands")
            execution_status = execute_commands(command_list, device, widget_dict, attribute_to_element_map,
                                                package_name)
            flags[3] = add_commands(executed_commands, command_list)

            if command_list:
                last_executed_action = command_list[-1]

            logger.info(f'Execute command: {command_list}')

        action = command_list[0].get('action', '') if command_list else ''

        if not crash and action != 'check crash':
            crash = check_crash()
            if not crash:
                time.sleep(0.5)
                crash = check_error_keywords(get_current_hierarchy(device), package_name) \
                        or 'crashreport' in device.app_current()['activity'].lower()

    start_time, response_time, total_commands = execution_data
    log_and_save_history(reprot_file_name, start_time, response_time, total_commands, history, package_name, 'xxx',
                         logger)
    device.set_orientation("natural")
    return True



def main(device_port, report_file_name, bug_id, apk_info, total_res_file):
    bug_app_info = apk_info.get(bug_id, {})

    if not bug_app_info:
        with open(total_res_file, 'a+') as fw:
            fw.write(json.dumps({
                "report_file_name": report_file_name,
                "reproduce_res": "app info not found!",
            }) + '\n')
        return False


    log_dir = "your_log_path"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{bug_id}_reproduce.log")

    logger = logging.getLogger(__name__)
    logger.setLevel(level=logging.INFO)
    handler = logging.FileHandler(log_file)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    extracted_steps_file = f'your_extracted_steps_file_path'
    if not os.path.exists(extracted_steps_file):
        logger.info('Steps not found.')
        logger.removeHandler(handler)
        uninstall_app(bug_app_info, logger)
        return False

    apk_file_path = f'your_apk_file_path'
    if not os.path.exists(apk_file_path):
        logger.info('APK not found.')
        logger.removeHandler(handler)
        uninstall_app(bug_app_info, logger)
        return False

    extracted_steps = ''
    step_lines = get_extracted_steps(extracted_steps_file)

    if step_lines is None:
        logger.info('Steps can not be loaded.')
        with open(total_res_file, 'a+') as fw:
            fw.write(json.dumps({"report_file_name": report_file_name, "reproduce_res": "step load error!",
                                 'error': "Steps can not be loaded."}) + '\n')
        logger.removeHandler(handler)
        uninstall_app(bug_app_info, logger)
        return False

    for index, line in enumerate(step_lines):
        extracted_steps += f'{index}. {line.strip()} '

    try:
        need_ui_explore = True  
        launch_res = install_and_launch_app(apk_file_path, bug_app_info, logger, report_file_name)
        if not launch_res:
            logger.info('Failed to launch the app.')
            with open(total_res_file, 'a+') as fw:
                fw.write(json.dumps({"report_file_name": report_file_name, "reproduce_res": "launch error!",
                                     'error': "Failed to launch the app."}) + '\n')
            logger.removeHandler(handler)
            uninstall_app(bug_app_info, logger)
            return False
        res = reproduce_bug(device_port, report_file_name, bug_app_info, extracted_steps, need_ui_explore, logger)
        uninstall_app(bug_app_info, logger)

        if res == False:
            need_ui_explore = False
            launch_res = install_and_launch_app(apk_file_path, bug_app_info, logger, report_file_name)
            if not launch_res:
                logger.info('Failed to launch the app.')
                with open(total_res_file, 'a+') as fw:
                    fw.write(json.dumps({"report_file_name": report_file_name, "reproduce_res": "launch error!",
                                         'error': "Failed to launch the app."}) + '\n')
                logger.removeHandler(handler)
                uninstall_app(bug_app_info, logger)
                return False
            reproduce_bug(device_port, report_file_name, bug_app_info, extracted_steps, need_ui_explore, logger)
            uninstall_app(bug_app_info, logger)

        if res:
            print('Successfully reproduced!')
            with open(total_res_file, 'a+') as fw:
                fw.write(json.dumps({"report_file_name": report_file_name, "reproduce_res": "successfully reproduced!",
                                     'error': ""}) + '\n')

    except FunctionTimedOut:
        logger.info("Timeout!")
        with open(total_res_file, 'a+') as fw:
            fw.write(json.dumps(
                {"report_file_name": report_file_name, "reproduce_res": "timeout!", 'error': "timeout"}) + '\n')
    except Exception as e:
        logger.info("Exception happened!")
        logger.info(str(e))
        # raise e
        with open(total_res_file, 'a+') as fw:
            fw.write(json.dumps(
                {"report_file_name": report_file_name, "reproduce_res": "exception!", 'error': str(e)}) + '\n')

    logger.removeHandler(handler)
    uninstall_app(bug_app_info, logger)






if __name__ == "__main__":
    device_id_port = "your_device_id_port"
    report_path = "path/to/single_report.txt"
    apk_file_path = "path/to/apk_info.json"
    output_file = "path/to/result.json"

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    main(device_id_port, report_path, bug_id, apk_info, total_res_file)


