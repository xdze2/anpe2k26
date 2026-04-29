from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from anpe.config import settings

_model = OpenAIChatModel(
    settings.openrouter_model,
    provider=OpenAIProvider(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
    ),
)

agent = Agent(
    _model,
    system_prompt=(
        "Tu es l'Assistant Numérique Pour l'Emploi (ANPE). "
        "Tu aides les utilisateurs dans leurs démarches de recherche d'emploi, "
        "rédaction de CV, préparation aux entretiens, et orientation professionnelle. "
        "Réponds en français sauf si l'utilisateur s'adresse à toi dans une autre langue."
    ),
)
