import asyncio
import asyncpg
import ssl
from config import DATABASE

async def test_connection():
    try:
        # Création d'un contexte SSL par défaut
        ssl_context = ssl.create_default_context()

        print("Tentative de connexion avec les paramètres suivants :")
        print(f"User: {DATABASE['user']}")
        print(f"Host: {DATABASE['host']}")
        print(f"Database: {DATABASE['database']}")
        print(f"Port: {DATABASE['port']}")
        print("SSL: Activé (SSL/TLS requis par le serveur)")

        conn = await asyncpg.connect(
            user=DATABASE['user'],
            password=DATABASE['password'],
            database=DATABASE['database'],
            host=DATABASE['host'],
            port=DATABASE['port'],
            ssl=ssl_context
        )
        print("Connexion réussie !")

        # Exécution d'une requête simple pour tester la connexion
        result = await conn.fetch("SELECT 1 AS test")
        print("Résultat de la requête :", result)

        await conn.close()
    except Exception as e:
        print("Erreur lors de la connexion :", e)

if __name__ == "__main__":
    asyncio.run(test_connection())
