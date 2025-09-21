from utils import get_logcat
from datetime import datetime

def log_and_save_history(reprot_file_name, start_time, response_time, total_commands, history, package_name,
                         error_type, logger):
    execution_time = (datetime.now() - start_time).total_seconds()
    print(f"!!!{error_type}!!!. Execution time: {execution_time} seconds")
    print(f"!!!Total Commands: {total_commands}")
    logger.info(f"!!!{error_type}!!!. Execution time: {execution_time} seconds")
    logger.info(f"!!!Total Commands: {total_commands}")


def check_crash(device_port):
    logcat = get_logcat(device_port)
    if 'FATAL' or "fatal" in logcat:
        print('Found fatal')
        return True
    return False
