import asyncio
import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
BASE_URL = "https://openrouter.ai/api/v1"
API_KEY = os.environ["OPENROUTER_API_KEY"]

model = OpenAIModel(
    MODEL,
    provider=OpenAIProvider(base_url=BASE_URL, api_key=API_KEY),
)

agent = Agent(
    model,
    system_prompt=(
        "Tu es l'Assistant Numérique Pour l'Emploi (ANPE). "
        "Tu aides les utilisateurs dans leurs démarches de recherche d'emploi, "
        "rédaction de CV, préparation aux entretiens, et orientation professionnelle. "
        "Réponds en français sauf si l'utilisateur s'adresse à toi dans une autre langue."
    ),
)


async def main() -> None:
    print("ANPE — Assistant Numérique Pour l'Emploi")
    print("Tapez 'quit' pour quitter.\n")

    while True:
        user_input = input("Vous: ").strip()
        if user_input.lower() in {"quit", "exit", "q"}:
            break
        if not user_input:
            continue

        result = await agent.run(user_input)
        print(f"ANPE: {result.output}\n")


if __name__ == "__main__":
    asyncio.run(main())
