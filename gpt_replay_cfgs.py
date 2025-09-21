import datetime
import math
import time
import tiktoken
import json
import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from typing import List, Dict, Any


llm = ChatOpenAI(
    model="your_model",
    openai_api_key="your_api_key",
    openai_api_base="your_api_base",
    max_tokens=1024,
    temperature=1
)

prompt_template = PromptTemplate(
    input_variables=["input_text"],
    template="{input_text}"
)

chain = (
        {"input_text": RunnablePassthrough()}
        | prompt_template
        | llm
        | StrOutputParser()
)


def count_tokens(message: str) -> int:
    encoding = tiktoken.encoding_for_model("gpt-4")
    tokens_integer = encoding.encode(message)
    return len(tokens_integer)


def count_chat_history_tokens(chat_history: List[Dict[str, str]]) -> int:
    total_tokens = 0
    for message in chat_history:
        total_tokens += count_tokens(message['content'])
        total_tokens += count_tokens(message['role'])
    return total_tokens


def truncate_message(message: str, n: int) -> tuple:
    encoding = tiktoken.encoding_for_model("gpt-4")
    tokens_integer = encoding.encode(message)
    if len(tokens_integer) <= n:
        return False, None
    else:
        truncated_tokens = tokens_integer[:math.floor(n)]
        truncated_message = encoding.decode(truncated_tokens)
        return True, truncated_message


def process_history(prompt: str, history: List[Dict[str, str]], max_tokens: int, threshold: float) -> List[
    Dict[str, str]]:
    tokens_in_chat_history = count_chat_history_tokens(history)

    if tokens_in_chat_history > math.floor(max_tokens * threshold):
        last_prompt_message = history[-1]['content']
        if count_tokens(last_prompt_message) > 4000:
            del history[-1]
            truncated, truncated_message = truncate_message(last_prompt_message, (
                    max_tokens - count_chat_history_tokens(history)) * threshold)
            history.append({"role": "user", "content": truncated_message})

        print('summarize==========================================')
        history.append({"role": "user",
                        "content": 'The conversation is about to exceed the limit, before we continue the reproduction process. Can you summarize the above conversation. Note that You shouldn\'t summarize the rules and keep the rules as original since the rules are the standards.'})

        conversation = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        message = chain.invoke(conversation)

        print(message)
        history.append({"role": "user", "content": message})

    history.append({"role": "user", "content": prompt})
    return history



def generate_text(prompt: str, history: List[Dict[str, str]], package_name: str = None, model: str = "deepseek-chat",
                  max_tokens: int = 128000, attempts: int = 3) -> tuple:
    history = process_history(prompt, history, max_tokens, threshold=0.75)

    for times in range(attempts):
        try:
            conversation = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
            response = chain.invoke(conversation)
            history.append({"role": "assistant", "content": response})
            return response, history
        except Exception as e:
            print(f"Attempt {times + 1} failed with error: {str(e)}")
            if times < 2:
                if package_name is not None:
                    save_chat_history(history, package_name)
                print(f"Take a 60*{times + 1} seconds break before the next attempt...")
                time.sleep(60 * (times + 1))
            else:
                print(f"All {attempts} attempts failed. Please try again later.")
                if package_name is not None:
                    save_chat_history(history, package_name)
                raise e


def save_chat_history(history: List[Dict[str, str]], package_name: str) -> None:
    os.makedirs("./chat_history", exist_ok=True)

    curr_time = datetime.datetime.now()
    curr_time_string = curr_time.strftime("%Y-%m-%d %H-%M-%S")
    file_name = f"./chat_history/{package_name}_chat_{curr_time_string}.json"
    with open(file_name, 'w', encoding='utf-8') as file:
        json.dump(history, file, ensure_ascii=False, indent=2)

def get_message(response: Any) -> Any:
    try:
        if response is None:
            return None
        if isinstance(response, list):
            return response
        if isinstance(response, str):
            try:
                parsed = json.loads(response)
                if isinstance(parsed, list):
                    return parsed
                return response
            except json.JSONDecodeError:
                return response
        if hasattr(response, 'choices'):
            try:
                return response.choices[0].message.content
            except AttributeError:
                try:
                    return response["choices"][0]["message"]["content"]
                except (KeyError, TypeError):
                    return response

        if isinstance(response, dict):
            if "choices" in response:
                try:
                    return response["choices"][0]["message"]["content"]
                except (KeyError, TypeError):
                    return response

        return response

    except Exception as e:
        print(f"Error processing response: {str(e)}")
        return response


