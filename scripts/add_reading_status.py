"""
Быстрый фикс: добавляет колонку reading_status в таблицу bookmarks.
Запускать из корня проекта:
    python scripts/add_reading_status.py
"""
import asyncio
from sqlalchemy import text
from app.db.base import engine


async def main():
    async with engine.begin() as conn:
        # Проверяем, есть ли уже колонка
        result = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'bookmarks' AND column_name = 'reading_status'
        """))
        exists = result.fetchone()

        if exists:
            print("✅ Колонка reading_status уже существует — ничего делать не нужно.")
        else:
            await conn.execute(text("""
                ALTER TABLE bookmarks
                ADD COLUMN reading_status VARCHAR(30) NOT NULL DEFAULT 'reading'
            """))
            print("✅ Колонка reading_status успешно добавлена в таблицу bookmarks!")

        # Проверяем following_count в users
        result2 = await conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'following_count'
        """))
        exists2 = result2.fetchone()

        if exists2:
            print("✅ Колонка following_count в users уже существует.")
        else:
            await conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN following_count INTEGER NOT NULL DEFAULT 0
            """))
            print("✅ Колонка following_count успешно добавлена в таблицу users!")


if __name__ == "__main__":
    asyncio.run(main())
