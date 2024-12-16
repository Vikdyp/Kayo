# services/user_service.py

from utils.database import database
import logging

class UserService:
    @staticmethod
    async def register_user(user_id: int, name: str) -> bool:
        query = """
        INSERT INTO users (user_id, name)
        VALUES ($1, $2)
        ON CONFLICT (user_id) DO NOTHING;
        """
        try:
            await database.execute(query, user_id, name)
            logging.info(f"Utilisateur {name} enregistré.")
            return True
        except Exception as e:
            logging.error(f"Erreur en enregistrant l'utilisateur {name}: {e}")
            return False

    @staticmethod
    async def get_user(user_id: int):
        query = "SELECT * FROM users WHERE user_id = $1;"
        try:
            return await database.fetchrow(query, user_id)
        except Exception as e:
            logging.error(f"Erreur en récupérant l'utilisateur {user_id}: {e}")
            return None

    @staticmethod
    async def update_user_name(user_id: int, new_name: str) -> bool:
        query = """
        UPDATE users
        SET name = $1
        WHERE user_id = $2;
        """
        try:
            await database.execute(query, new_name, user_id)
            logging.info(f"Nom de l'utilisateur {user_id} mis à jour en {new_name}.")
            return True
        except Exception as e:
            logging.error(f"Erreur en mettant à jour le nom de l'utilisateur {user_id}: {e}")
            return False

    @staticmethod
    async def delete_user(user_id: int) -> bool:
        query = "DELETE FROM users WHERE user_id = $1;"
        try:
            await database.execute(query, user_id)
            logging.info(f"Utilisateur {user_id} supprimé.")
            return True
        except Exception as e:
            logging.error(f"Erreur en supprimant l'utilisateur {user_id}: {e}")
            return False
