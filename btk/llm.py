import os
import requests
import configparser

def load_btkrc_config():
    """
    Loads configuration from ~/.btkrc.

    Expects a section [llm] with at least 'endpoint' and 'api_key'.
    """
    config_path = os.path.expanduser("~/.btkrc")
    parser = configparser.ConfigParser()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Could not find config file at {config_path}")

    parser.read(config_path)

    if "llm" not in parser:
        raise ValueError(
            "Config file ~/.btkrc is missing the [llm] section. "
            "Please add it with 'endpoint' and 'api_key' keys."
        )

    endpoint = parser["llm"].get("endpoint", "")
    api_key = parser["llm"].get("api_key", "")
    model = parser["llm"].get("model", "gpt-3.5-turbo")

    if not endpoint or not api_key or not model:
        raise ValueError(
            "Please make sure your [llm] section in ~/.btkrc "
            "includes 'endpoint', 'api_key', and 'model' keys."
        )
    
    #print(f"{endpoint=}, {api_key=}, {model=}, {stream=}")

    return endpoint, api_key, model


def query_llm(prompt):
    """
    Queries an OpenAI-compatible LLM endpoint with the given prompt.

    :param prompt: The user query or conversation prompt text.
    :param model: The OpenAI model name to use, defaults to gpt-3.5-turbo.
    :param temperature: Sampling temperature, defaults to 0.7.
    :return: The JSON response from the endpoint.
    """
    endpoint, api_key, model = load_btkrc_config()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(endpoint, headers=headers, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        raise SystemError(f"Error calling LLM endpoint: {e}")

    return response.json()

