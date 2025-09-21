import subprocess
import uiautomator2 as u2
import xml.etree.ElementTree as ET
from collections import defaultdict
from ElementTree_hepler import *
import time
from my_gpt_deepseek import *
from handle_command import get_center_if_coordinate, click


def get_current_hierarchy(device):
    try:
        hierarchy_content = device.dump_hierarchy()
        hierarchy_content = ''.join(char for char in hierarchy_content if ord(char) < 128)
        with open('tmp', 'w') as file:
            file.write(hierarchy_content)
        xmlp = ET.XMLParser(encoding="utf-8")
        tree = ET.parse('tmp', parser=xmlp)
        return tree
    except Exception as e:
        return None


def get_container_type(current_type, className):
    if current_type != 'click':
        return current_type

    if '.Switch' in className:
        return 'switch_widget'
    elif 'Spinner' in className:
        return 'spinner'
    elif 'CheckBox' in className:
        return 'check_box'
    elif 'EditText' in className:
        return 'set_text'
    return 'click'


def process_group_general(root, parent_map, info, attr_to_elements):
    attr_to_group_elments = defaultdict(list)
    group, other_text, visited_elements = [], [], []
    type = 'click'

    if root.attrib.get('scrollable', 'false') == 'true':
        type = 'scrollable'

    for element in root.iter():
        visited_elements.append(element)
        clickable = element.attrib.get('clickable', 'false') == 'true'
        enabled = element.attrib.get('enabled', 'false') == 'true'
        text = element.attrib.get('text', '')
        content_desc = element.attrib.get('content-desc', '')
        resource_id = element.attrib.get('resource-id', '')
        className = element.attrib.get('class', '')

        type = get_container_type(type, className)
        className = className[className.rfind('.') + 1:]

        if type == 'set_text':
            if resource_id and text:
                group.insert(0, {className: resource_id})
                group.insert(0, text)
                attr_to_group_elments[resource_id].append(element)
            elif resource_id:
                group.insert(0, {className: resource_id})
            elif text:
                group.insert(0, text)
                attr_to_group_elments[text].append(element)
            else:
                bounds = element.attrib.get('bounds', '')
                group.insert(0, bounds)
                attr_to_group_elments[bounds].append(element)
        elif 'CheckBox' in className:
            if group != [] or other_text != []:
                group.append('status:checked' if element.attrib.get('checked', '') == 'true' else 'status:unchecked')
            elif text != '':
                group.extend(
                    [text, 'status:checked' if element.attrib.get('checked', '') == 'true' else 'status:unchecked'])
                attr_to_group_elments[text].append(element)
            elif resource_id:
                group.extend([resource_id,
                              'status:checked' if element.attrib.get('checked', '') == 'true' else 'status:unchecked'])
                attr_to_group_elments[resource_id].append(element)
            else:
                bounds = element.attrib.get('bounds', '')
                group.extend(
                    [bounds, 'status:checked' if element.attrib.get('checked', '') == 'true' else 'status:unchecked'])
                attr_to_group_elments[bounds].append(element)
        elif clickable:
            if content_desc:
                if enabled:
                    group.insert(0, {className: content_desc})
                else:
                    group.insert(0, 'disabled')
                    group.insert(0, {className: content_desc})
                attr_to_group_elments[content_desc].append(element)
            elif text:
                group.insert(0, text)
                attr_to_group_elments[text].append(element)
            elif resource_id:
                group.insert(0, {className: resource_id})
                attr_to_group_elments[resource_id].append(element)
            elif element.attrib.get('NAF', '') == 'true':
                bounds = element.attrib.get('bounds', '')
                group.insert(0, {'NAF': bounds})
                attr_to_group_elments[bounds].append(element)
        elif text and len(text) < 50:
            other_text.append(text)
            attr_to_group_elments[text].append(element)

    if other_text:
        group.extend(other_text)

    info['visited'].extend(visited_elements)

    for key, value in attr_to_group_elments.items():
        if key in attr_to_elements:
            attr_to_elements[key].extend(value)
        else:
            attr_to_elements[key] = value

    root_id = root.attrib.get('resource-id', '')
    if group != []:
        if root_id and root_id not in group:
            info[type].append(f"{root_id[root_id.rfind('/') + 1:]}:{group}")
        else:
            info[type].append(f"{group}")


def get_operable_elements(element, package_name, parent_map, info, attr_to_elements):
    if element.tag == 'node':
        if element.attrib.get('package', '') == 'com.android.systemui':
            return
        if element in info['visited']:
            return
        clickable = element.attrib.get('clickable', 'false') == 'true'
        long_clickable = element.attrib.get('long-clickable', 'false') == 'true'
        text = element.attrib.get('text', '')
        content_desc = element.attrib.get('content-desc', '')
        resource_id = element.attrib.get('resource-id', '')

        info['visited'].append(element)

        if 'toolbar' in resource_id:
            process_group_general(element, parent_map, info, attr_to_elements)
        elif (clickable or long_clickable) and not (text or content_desc or resource_id):
            process_group_general(element, parent_map, info, attr_to_elements)
        elif all_children_are_leaves(element) and is_clickable_or_has_clickable_children(element):
            process_group_general(element, parent_map, info, attr_to_elements)
        elif (clickable or long_clickable):
            if content_desc:
                info['click'].append([content_desc])
                if content_desc in attr_to_elements:
                    attr_to_elements[content_desc].append(element)
                else:
                    attr_to_elements.setdefault(content_desc, []).append(element)
            elif text and len(text) < 100:
                info['click'].append([text])
                if text in attr_to_elements:
                    attr_to_elements[text].append(element)
                else:
                    attr_to_elements.setdefault(text, []).append(element)
            elif resource_id:
                info['click'].append([resource_id])
                if resource_id in attr_to_elements:
                    attr_to_elements[resource_id].append(element)
                else:
                    attr_to_elements.setdefault(resource_id, []).append(element)
        elif text != '':
            info['local_text'].append(text)

    for child in element:
        get_operable_elements(child, package_name, parent_map, info, attr_to_elements)


def get_sequential_info(info, activity, orientation, toast):
    info['Other Widgets with Text in This Page'] = info["local_text"]
    del info["visited"]
    del info["local_text"]

    info = {k: v for k, v in info.items() if v != [] and v != [[]]}

    info_string = ''
    for key, values in info.items():
        if key == 'click_targets':
            continue
        info_string += f"{key} has the following group(s):"
        i = 1
        for v in values:
            info_string += f"{i}#.{v};"
            i += 1

    transition_prompt = ''
    if 'click_targets' in info:
        for identifier, target_info in info['click_targets'].items():
            new_activity = target_info['activity']
            summarization = target_info['summary']
            transition_prompt += f' Click {identifier} can lead to new activity: {new_activity}.'
            if summarization is not None:
                transition_prompt += f' The new activity can be summarized as: {summarization}'

    if toast is not None:
        return f"\n*Current Screen Information:  #Current Activity: {activity}. # UI Information:{info_string}. {transition_prompt} Toast message on the page: {toast}"
    else:
        return f"\n*Current Screen Information:  #Current Activity: {activity}.  # UI Information:{info_string}. {transition_prompt}"


def get_activity_info_from_dumpsys(device, package_name):
    try:
        result = device.shell(f'dumpsys activity {package_name} activities')
        activities = {}
        lines = result.output.lower().split('\n')
        current_task = None
        for line in lines:
            if 'taskrecord{' in line and package_name in line:
                current_task = line.strip()
            if 'activity' in line and package_name in line:
                activity_start = line.find(f'{package_name}/')
                if activity_start != -1:
                    activity_end = line.find(' ', activity_start)
                    if activity_end == -1:
                        activity_end = len(line)
                    activity_name = line[activity_start:activity_end]
                    intent_start = line.find('intent={')
                    if intent_start != -1:
                        intent_end = line.find('}', intent_start)
                        if intent_end != -1:
                            intent_info = line[intent_start:intent_end + 1]
                            activities[activity_name] = intent_info
                    else:
                        activities[activity_name] = None
        return activities
    except Exception as e:
        return {}


def get_element_priority(attr, element):
    resource_id = element.attrib.get('resource-id', '').lower()
    text = element.attrib.get('text', '').lower()
    content_desc = element.attrib.get('content-desc', '').lower()

    high_priority_keywords = ['menu', 'button', 'back', 'next', 'ok', 'cancel', 'done', 'submit']
    if any(keyword in resource_id or keyword in text or keyword in content_desc
           for keyword in high_priority_keywords):
        return 1

    if ((text and 2 <= len(text) <= 20) or
            (content_desc and 2 <= len(content_desc) <= 20) or
            (resource_id and len(resource_id.split('/')[-1]) <= 20)):
        return 2

    return 3


def fast_recovery_to_initial_state(device, package_name, initial_activity):
    current_activity = device.app_current()['activity']

    if current_activity == initial_activity:
        return True

    try:
        device.press("back")
        time.sleep(0.8)
        if device.app_current()['activity'] == initial_activity:
            return True
    except:
        pass

    try:
        device.app_stop(package_name)
        time.sleep(0.8)
        device.app_start(package_name)
        time.sleep(1)
        return device.app_current()['activity'] == initial_activity
    except:
        return False


def get_click_target_activities_hybrid(device, info, attr_to_elements, package_name, emulator_id,
                                       method='smart_hybrid'):

    click_targets = {}
    recovery_succeed = True
    total_detected = 0

    initial_activity = device.app_current()['activity']
    current_app = device.app_current()
    full_package = current_app['package']


    if method in ['smart_hybrid', 'click_only']:

        clickable_elements = []
        for attr, elements in attr_to_elements.items():
            if elements and len(elements) > 0:
                element = elements[0]
                clickable = element.attrib.get('clickable', 'false') == 'true'
                if clickable:
                    priority = get_element_priority(attr, element)
                    clickable_elements.append((attr, element, priority))


        clickable_elements.sort(key=lambda x: x[2])
        max_elements = 8 if method == 'smart_hybrid' else len(clickable_elements)
        clickable_elements = clickable_elements[:max_elements]


        start_time = time.time()
        time_limit = 15

        for i, (identifier, element, priority) in enumerate(clickable_elements):

            if time.time() - start_time > time_limit:
                break

            try:
                current_activity = device.app_current()['activity']

                if current_activity != initial_activity:
                    if not fast_recovery_to_initial_state(device, full_package, initial_activity):
                        break

                try:
                    before_hierarchy = device.dump_hierarchy()
                    before_length = len(before_hierarchy)
                except:
                    before_hierarchy = ""
                    before_length = 0

                bounds = element.attrib.get('bounds', '')
                if not bounds:
                    continue

                coordinates = get_center_if_coordinate(bounds)
                if not coordinates:
                    continue

                click(device, coordinates)
                time.sleep(1)  

                new_activity = device.app_current()['activity']

                activity_changed = new_activity != initial_activity
                ui_changed = False

                try:
                    after_hierarchy = device.dump_hierarchy()
                    after_length = len(after_hierarchy)

                    length_change = abs(after_length - before_length) / max(before_length, 1)
                    if length_change > 0.1:  
                        ui_changed = True

                    ui_indicators = ['dialog', 'popup', 'menu', 'sheet', 'spinner', 'dropdown']
                    for indicator in ui_indicators:
                        if indicator in after_hierarchy.lower() and indicator not in before_hierarchy.lower():
                            ui_changed = True
                            break

                except Exception as e:
                    print(f"DEBUG: UI comparison failed: {e}")

                if activity_changed or ui_changed:
                   try:
                        d = u2.connect(emulator_id)
                        page_source = d.dump_hierarchy(compressed=True, pretty=True)
                        
                        summarize_prompt = f'The current screen information is as follows: \n```xml{page_source}\n```\n Please summarize the function of this page.'
                        
                        from my_gpt_deepseek import generate_text, get_message
                        response, history = generate_text(summarize_prompt, [], package_name)
                        summarization_response = get_message(response)
                        
                        print(f"DEBUG: LLM Summary for {identifier}: {summarization_response}")
                        
                    except Exception as e:
                        print(f"DEBUG: Failed to generate LLM summary: {e}")
                        summarization_response = None

                    if activity_changed:
                        target_activity = new_activity
                        confidence = 0.
                        change_type = "Activity change"
                    else:
                        target_activity = f"{initial_activity}_UI_CHANGE"
                        confidence = 0.7
                        change_type = "UI change"

                    if summarization_response:
                        summary = summarization_response
                    else:
                        summary = f"{change_type}: {identifier}"

                    click_targets[identifier] = {
                        'activity': target_activity,
                        'summary': summary,
                        'method': 'dynamic',
                        'confidence': confidence,
                        'bounds': bounds
                    }
                    total_detected += 1

                    if activity_changed:
                        if not fast_recovery_to_initial_state(device, full_package, initial_activity):
                            break
                else:
                    print(f"DEBUG: No significant change detected for {identifier}")

            except Exception as e:
                try:
                    fast_recovery_to_initial_state(device, full_package, initial_activity)
                except:
                    pass


    if method in ['smart_hybrid', 'analyze_only']:

        static_processed = 0
        static_found = 0

        for attr, elements in attr_to_elements.items():
            if elements and len(elements) > 0:
                element = elements[0]
                clickable = element.attrib.get('clickable', 'false') == 'true'

                if clickable:
                    static_processed += 1

                    if attr in click_targets:
                        continue

                    resource_id = element.attrib.get('resource-id', '')
                    text = element.attrib.get('text', '')
                    content_desc = element.attrib.get('content-desc', '')


                    predicted_target = None
                    confidence = 0.5

                    if content_desc:
                        predicted_target = f"{initial_activity}_{content_desc.replace(' ', '_')}"
                        confidence = 0.6
                    elif text:
                        predicted_target = f"{initial_activity}_{text.replace(' ', '_')}"
                        confidence = 0.6
                    elif resource_id:
                        id_part = resource_id.split('/')[-1] if '/' in resource_id else resource_id
                        predicted_target = f"{initial_activity}_{id_part}"
                        confidence = 0.5
                    else:
                        predicted_target = f"{initial_activity}_Unknown"
                        confidence = 0.3

                    click_targets[attr] = {
                        'activity': predicted_target,
                        'method': 'static',
                        'confidence': confidence,
                        'summary': f"Static prediction: {attr}"
                    }
                    total_detected += 1
                    static_found += 1


    return click_targets, recovery_succeed, total_detected



def get_screen_information(device, attribute_to_element_map, package_name,emulator_id, check_clickable,
                           activity_detection_method='smart_hybrid'):
    start_time = time.time()

    try:
        toast = device.toast.get_message(1, 1, None)
    except:
        toast = None

    tree = get_current_hierarchy(device)
    if not tree:
        return None, None, False, 0

    root = tree.getroot()
    parent_map = build_parent_map(tree)
    info = {'toolbar': [], 'set_text': [], 'click': [], 'spinner': [], 'check_box': [], 'switch_widget': [],
            'scrollable': [], 'local_text': [], 'visited': [], 'click_targets': []}

    activity = device.app_current()['activity']
    get_operable_elements(root, package_name, parent_map, info, attribute_to_element_map)

    recovery_succeed = True
    total_detected = 0

    if check_clickable:
        click_targets, recovery_succeed, total_detected = get_click_target_activities_hybrid(
            device, info, attribute_to_element_map, package_name, emulator_id, method=activity_detection_method)
        info.update({"click_targets": click_targets})

    if activity_detection_method != 'click_only':
        try:
            info['all_activities'] = get_activity_info_from_dumpsys(device, package_name)
        except:
            info['all_activities'] = {}

    elapsed_time = time.time() - start_time

    return info, get_sequential_info(info, activity, device.orientation, toast), recovery_succeed, total_detected