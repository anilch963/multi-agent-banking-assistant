from functools import lru_cache

from langchain_openai import ChatOpenAI

from app import config


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    kwargs = {"model": config.OPENAI_MODEL}
    if config.OPENAI_TEMPERATURE not in (None, ""):
        kwargs["temperature"] = float(config.OPENAI_TEMPERATURE)
    return ChatOpenAI(**kwargs)
