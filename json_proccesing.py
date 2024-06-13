import json
from typing import Dict

def load_data_json(file_path='data.json'):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        data = {}

    return data


def save_data_json(data, file_path='data.json'):
    with open(file_path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
        

def delete_json_data(key, file_path='data.json'):
    data = load_data_json(file_path)
    
    if key in data:
        del data[key]
        save_data_json(data, file_path)