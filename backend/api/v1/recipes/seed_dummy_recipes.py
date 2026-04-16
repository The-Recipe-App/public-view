# api/v1/recipes/seed.py
#
# Admin-only endpoint to bulk-insert hardcoded dummy recipes.
# Mount this router only in non-production environments.
# Call: POST /api/v1/recipes/seed  (no body needed, just auth cookie)

from datetime import datetime, timezone
import os
import uuid
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from database.main.core.session import get_async_session
from database.main.core.models import (
    User,
    Recipe,
    Ingredient,
    RecipeStep,
    RecipeLineageSnapshot,
    Activity,
    RecipeMedia,
    MediaType,
)
from api.v1.auth.utils.dependencies import get_current_user
from api.v1.media.storage import s3

router = APIRouter()

IS_PROD = os.getenv("ENV") == "production"

# Root of the project (two levels up from this file: api/v1/recipes/seed.py -> root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DUMMY_IMAGE_DIR = _PROJECT_ROOT / "extra_files" / "dummy_recipe_images"

# ── Hardcoded dummy recipes ───────────────────────────────────────────────────
# Each recipe may optionally declare an "image_filename" that must exist inside
# DUMMY_IMAGE_DIR.  The file should be named after the recipe ID, e.g. "1.jpg",
# "2.png", etc.  If the file is missing the seeder logs a warning and continues.

DUMMY_RECIPES = [
    {
        "title": "Classic Margherita Pizza",
        "body": "A simple, delicious Neapolitan-style pizza.",
        "is_draft": False,
        "image_filename": "1.jpg",
        "ingredients": [
            {"name": "00 flour",             "is_animal": False, "is_allergen": True},
            {"name": "fresh mozzarella",     "is_animal": True,  "is_allergen": True},
            {"name": "san marzano tomatoes", "is_animal": False, "is_allergen": False},
            {"name": "fresh basil",          "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Mix flour, water, salt and yeast. Knead until smooth.",          "technique": "kneading",   "estimated_minutes": 15},
            {"step_number": 2, "instruction": "Stretch dough, add crushed tomatoes and torn mozzarella.",       "technique": "stretching", "estimated_minutes": 10},
            {"step_number": 3, "instruction": "Bake at 500F on a preheated stone for 8-10 minutes.",            "technique": "baking",     "estimated_minutes": 10},
        ],
    },
    {
        "title": "Beef Tacos with Pico de Gallo",
        "body": "Street-style beef tacos with fresh homemade salsa.",
        "is_draft": False,
        "image_filename": "2.jpg",
        "ingredients": [
            {"name": "ground beef",    "is_animal": True,  "is_allergen": False},
            {"name": "corn tortillas", "is_animal": False, "is_allergen": True},
            {"name": "roma tomatoes",  "is_animal": False, "is_allergen": False},
            {"name": "white onion",    "is_animal": False, "is_allergen": False},
            {"name": "cilantro",       "is_animal": False, "is_allergen": False},
            {"name": "lime",           "is_animal": False, "is_allergen": False},
            {"name": "cumin",          "is_animal": False, "is_allergen": False},
            {"name": "chili powder",   "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Dice tomatoes, onion, and cilantro. Combine with lime juice and salt to make pico de gallo.", "technique": "dicing",      "estimated_minutes": 10},
            {"step_number": 2, "instruction": "Brown ground beef in a skillet over medium-high heat. Season with cumin, chili powder, and salt.", "technique": "sautéing", "estimated_minutes": 10},
            {"step_number": 3, "instruction": "Warm tortillas on a dry skillet. Fill with beef and top with pico de gallo.",                 "technique": "assembling", "estimated_minutes": 5},
        ],
    },
    {
        "title": "Creamy Mushroom Risotto",
        "body": "A rich and comforting Italian risotto with earthy mushrooms.",
        "is_draft": False,
        "image_filename": "3.jpg",
        "ingredients": [
            {"name": "arborio rice",      "is_animal": False, "is_allergen": False},
            {"name": "cremini mushrooms", "is_animal": False, "is_allergen": False},
            {"name": "parmesan cheese",   "is_animal": True,  "is_allergen": True},
            {"name": "dry white wine",    "is_animal": False, "is_allergen": True},
            {"name": "vegetable broth",   "is_animal": False, "is_allergen": False},
            {"name": "shallots",          "is_animal": False, "is_allergen": False},
            {"name": "butter",            "is_animal": True,  "is_allergen": True},
            {"name": "garlic",            "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Sauté shallots and garlic in butter until translucent. Add mushrooms and cook until golden.", "technique": "sautéing", "estimated_minutes": 10},
            {"step_number": 2, "instruction": "Add arborio rice and toast for 2 minutes. Deglaze with white wine.",                          "technique": "toasting", "estimated_minutes": 5},
            {"step_number": 3, "instruction": "Add warm broth one ladle at a time, stirring continuously until absorbed. Repeat until rice is al dente.", "technique": "stirring", "estimated_minutes": 20},
            {"step_number": 4, "instruction": "Remove from heat, fold in butter and parmesan. Season and serve immediately.",                "technique": "folding",  "estimated_minutes": 5},
        ],
    },
    {
        "title": "Classic French Omelette",
        "body": "A silky, custardy omelette in the traditional French style.",
        "is_draft": False,
        "image_filename": "4.jpg",
        "ingredients": [
            {"name": "eggs",         "is_animal": True,  "is_allergen": True},
            {"name": "butter",       "is_animal": True,  "is_allergen": True},
            {"name": "fresh chives", "is_animal": False, "is_allergen": False},
            {"name": "salt",         "is_animal": False, "is_allergen": False},
            {"name": "white pepper", "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Whisk eggs vigorously with salt and white pepper until fully combined and slightly frothy.",          "technique": "whisking", "estimated_minutes": 3},
            {"step_number": 2, "instruction": "Melt butter in a non-stick pan over medium heat until foaming. Pour in eggs.",                        "technique": "melting",  "estimated_minutes": 2},
            {"step_number": 3, "instruction": "Stir eggs constantly with a spatula while shaking the pan. Remove from heat when just set but still custardy.", "technique": "stirring", "estimated_minutes": 3},
            {"step_number": 4, "instruction": "Roll the omelette onto a plate, garnish with chives and serve immediately.",                          "technique": "rolling",  "estimated_minutes": 2},
        ],
    },
    {
        "title": "Lemon Herb Roasted Chicken",
        "body": "Juicy roasted chicken with bright lemon and fragrant herbs.",
        "is_draft": False,
        "image_filename": "5.jpg",
        "ingredients": [
            {"name": "whole chicken",  "is_animal": True,  "is_allergen": False},
            {"name": "lemon",          "is_animal": False, "is_allergen": False},
            {"name": "fresh rosemary", "is_animal": False, "is_allergen": False},
            {"name": "fresh thyme",    "is_animal": False, "is_allergen": False},
            {"name": "garlic",         "is_animal": False, "is_allergen": False},
            {"name": "olive oil",      "is_animal": False, "is_allergen": False},
            {"name": "salt",           "is_animal": False, "is_allergen": False},
            {"name": "black pepper",   "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Pat chicken dry. Rub all over with olive oil, salt, pepper, and minced garlic.", "technique": "rubbing",  "estimated_minutes": 10},
            {"step_number": 2, "instruction": "Stuff cavity with lemon halves, rosemary, and thyme sprigs.",                   "technique": "stuffing", "estimated_minutes": 5},
            {"step_number": 3, "instruction": "Roast at 425F for 50-60 minutes until juices run clear and skin is golden brown.", "technique": "roasting", "estimated_minutes": 60},
            {"step_number": 4, "instruction": "Rest for 10 minutes before carving.",                                           "technique": "resting",  "estimated_minutes": 10},
        ],
    },
    {
        "title": "Miso Glazed Salmon",
        "body": "Tender salmon fillets with a savory-sweet miso glaze, broiled to perfection.",
        "is_draft": False,
        "image_filename": "6.jpg",
        "ingredients": [
            {"name": "salmon fillets",   "is_animal": True,  "is_allergen": True},
            {"name": "white miso paste", "is_animal": False, "is_allergen": True},
            {"name": "mirin",            "is_animal": False, "is_allergen": True},
            {"name": "sake",             "is_animal": False, "is_allergen": True},
            {"name": "sugar",            "is_animal": False, "is_allergen": False},
            {"name": "sesame seeds",     "is_animal": False, "is_allergen": True},
            {"name": "scallions",        "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Whisk miso, mirin, sake, and sugar together until smooth. Coat salmon fillets and marinate for at least 30 minutes.", "technique": "marinating", "estimated_minutes": 30},
            {"step_number": 2, "instruction": "Place salmon on a lined baking sheet. Broil on high for 5-7 minutes until caramelized and cooked through.",           "technique": "broiling",   "estimated_minutes": 7},
            {"step_number": 3, "instruction": "Garnish with sesame seeds and sliced scallions. Serve over steamed rice.",                                            "technique": "garnishing", "estimated_minutes": 2},
        ],
    },
    {
        "title": "Shakshuka",
        "body": "Eggs poached in a spiced tomato and pepper sauce — perfect for any meal.",
        "is_draft": False,
        "image_filename": "7.jpg",
        "ingredients": [
            {"name": "eggs",                    "is_animal": True,  "is_allergen": True},
            {"name": "canned crushed tomatoes", "is_animal": False, "is_allergen": False},
            {"name": "red bell pepper",         "is_animal": False, "is_allergen": False},
            {"name": "yellow onion",            "is_animal": False, "is_allergen": False},
            {"name": "garlic",                  "is_animal": False, "is_allergen": False},
            {"name": "cumin",                   "is_animal": False, "is_allergen": False},
            {"name": "smoked paprika",          "is_animal": False, "is_allergen": False},
            {"name": "feta cheese",             "is_animal": True,  "is_allergen": True},
            {"name": "olive oil",               "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Sauté onion and bell pepper in olive oil until softened. Add garlic, cumin, and paprika; cook 1 minute.", "technique": "sautéing",  "estimated_minutes": 10},
            {"step_number": 2, "instruction": "Pour in crushed tomatoes and simmer until sauce thickens, about 10 minutes. Season with salt.",            "technique": "simmering", "estimated_minutes": 10},
            {"step_number": 3, "instruction": "Make wells in the sauce and crack eggs into them. Cover and cook until whites are set but yolks are still runny.", "technique": "poaching", "estimated_minutes": 8},
            {"step_number": 4, "instruction": "Crumble feta on top and serve directly from the pan with crusty bread.",                                  "technique": "garnishing","estimated_minutes": 2},
        ],
    },
    {
        "title": "Thai Green Curry",
        "body": "Aromatic and creamy Thai green curry with vegetables and jasmine rice.",
        "is_draft": False,
        "image_filename": "8.jpg",
        "ingredients": [
            {"name": "green curry paste",  "is_animal": False, "is_allergen": False},
            {"name": "coconut milk",       "is_animal": False, "is_allergen": False},
            {"name": "chicken breast",     "is_animal": True,  "is_allergen": False},
            {"name": "zucchini",           "is_animal": False, "is_allergen": False},
            {"name": "baby spinach",       "is_animal": False, "is_allergen": False},
            {"name": "fish sauce",         "is_animal": True,  "is_allergen": True},
            {"name": "palm sugar",         "is_animal": False, "is_allergen": False},
            {"name": "kaffir lime leaves", "is_animal": False, "is_allergen": False},
            {"name": "Thai basil",         "is_animal": False, "is_allergen": False},
            {"name": "jasmine rice",       "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Fry green curry paste in a dry wok over high heat for 1 minute until fragrant.",                     "technique": "frying",      "estimated_minutes": 2},
            {"step_number": 2, "instruction": "Pour in coconut milk and bring to a simmer. Add kaffir lime leaves, fish sauce, and sugar.",         "technique": "simmering",   "estimated_minutes": 5},
            {"step_number": 3, "instruction": "Add sliced chicken and zucchini. Cook until chicken is cooked through, about 8 minutes.",            "technique": "simmering",   "estimated_minutes": 8},
            {"step_number": 4, "instruction": "Stir in spinach and Thai basil. Serve over steamed jasmine rice.",                                   "technique": "assembling",  "estimated_minutes": 3},
        ],
    },
    {
        "title": "Classic Hummus",
        "body": "Smooth, creamy homemade hummus from scratch with tahini and lemon.",
        "is_draft": False,
        "image_filename": "9.jpg",
        "ingredients": [
            {"name": "dried chickpeas", "is_animal": False, "is_allergen": False},
            {"name": "tahini",          "is_animal": False, "is_allergen": True},
            {"name": "lemon juice",     "is_animal": False, "is_allergen": False},
            {"name": "garlic",          "is_animal": False, "is_allergen": False},
            {"name": "olive oil",       "is_animal": False, "is_allergen": False},
            {"name": "cumin",           "is_animal": False, "is_allergen": False},
            {"name": "ice water",       "is_animal": False, "is_allergen": False},
            {"name": "salt",            "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Soak dried chickpeas overnight, then boil until very tender, about 1.5 hours.",                              "technique": "boiling",  "estimated_minutes": 90},
            {"step_number": 2, "instruction": "Reserve cooking liquid. Peel chickpeas for a smoother texture.",                                             "technique": "peeling",  "estimated_minutes": 15},
            {"step_number": 3, "instruction": "Blend chickpeas, tahini, lemon juice, garlic, cumin, and salt. Stream in ice water until silky smooth.",     "technique": "blending", "estimated_minutes": 5},
            {"step_number": 4, "instruction": "Spread in a bowl, drizzle with olive oil, and dust with paprika to serve.",                                  "technique": "plating",  "estimated_minutes": 2},
        ],
    },
    {
        "title": "Spaghetti Carbonara",
        "body": "The authentic Roman pasta — no cream, just eggs, pecorino, and guanciale.",
        "is_draft": False,
        "image_filename": "10.jpg",
        "ingredients": [
            {"name": "spaghetti",       "is_animal": False, "is_allergen": True},
            {"name": "guanciale",       "is_animal": True,  "is_allergen": False},
            {"name": "eggs",            "is_animal": True,  "is_allergen": True},
            {"name": "pecorino romano", "is_animal": True,  "is_allergen": True},
            {"name": "black pepper",    "is_animal": False, "is_allergen": False},
            {"name": "salt",            "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Cook spaghetti in heavily salted boiling water until al dente. Reserve 1 cup pasta water.",                       "technique": "boiling",   "estimated_minutes": 10},
            {"step_number": 2, "instruction": "Render guanciale in a pan over medium heat until crispy. Remove from heat.",                                      "technique": "rendering", "estimated_minutes": 8},
            {"step_number": 3, "instruction": "Whisk eggs and grated pecorino with generous black pepper to form a paste.",                                      "technique": "whisking",  "estimated_minutes": 3},
            {"step_number": 4, "instruction": "Toss hot pasta with guanciale off the heat. Add egg mixture, splash in pasta water, and toss rapidly until creamy.", "technique": "tossing", "estimated_minutes": 3},
        ],
    },
    {
        "title": "Chocolate Lava Cake",
        "body": "Individual warm chocolate cakes with a molten center, ready in 20 minutes.",
        "is_draft": False,
        "image_filename": "11.jpg",
        "ingredients": [
            {"name": "dark chocolate (70%)", "is_animal": False, "is_allergen": True},
            {"name": "butter",               "is_animal": True,  "is_allergen": True},
            {"name": "eggs",                 "is_animal": True,  "is_allergen": True},
            {"name": "egg yolks",            "is_animal": True,  "is_allergen": True},
            {"name": "sugar",                "is_animal": False, "is_allergen": False},
            {"name": "all-purpose flour",    "is_animal": False, "is_allergen": True},
            {"name": "salt",                 "is_animal": False, "is_allergen": False},
            {"name": "vanilla extract",      "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Melt chocolate and butter together over a double boiler or in the microwave in 30-second bursts. Stir until smooth.", "technique": "melting",  "estimated_minutes": 5},
            {"step_number": 2, "instruction": "Whisk eggs, yolks, and sugar until combined. Fold in chocolate mixture, then flour and salt.",                        "technique": "folding",  "estimated_minutes": 5},
            {"step_number": 3, "instruction": "Pour batter into buttered and floured ramekins. Chill for at least 30 minutes.",                                      "technique": "chilling", "estimated_minutes": 30},
            {"step_number": 4, "instruction": "Bake at 425F for exactly 12 minutes. Invert onto plates and serve immediately.",                                      "technique": "baking",   "estimated_minutes": 12},
        ],
    },
    {
        "title": "Vegetable Stir-Fry with Tofu",
        "body": "Crispy tofu and vibrant vegetables in a savory ginger-soy sauce.",
        "is_draft": False,
        "image_filename": "12.jpg",
        "ingredients": [
            {"name": "firm tofu",      "is_animal": False, "is_allergen": True},
            {"name": "broccoli",       "is_animal": False, "is_allergen": False},
            {"name": "snap peas",      "is_animal": False, "is_allergen": False},
            {"name": "carrots",        "is_animal": False, "is_allergen": False},
            {"name": "soy sauce",      "is_animal": False, "is_allergen": True},
            {"name": "sesame oil",     "is_animal": False, "is_allergen": True},
            {"name": "fresh ginger",   "is_animal": False, "is_allergen": False},
            {"name": "garlic",         "is_animal": False, "is_allergen": False},
            {"name": "cornstarch",     "is_animal": False, "is_allergen": False},
            {"name": "vegetable oil",  "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Press tofu for 30 minutes. Cut into cubes, toss in cornstarch, and pan-fry until golden on all sides.", "technique": "pan-frying",  "estimated_minutes": 15},
            {"step_number": 2, "instruction": "Mix soy sauce, sesame oil, minced ginger, garlic, and a pinch of sugar for the sauce.",                 "technique": "mixing",      "estimated_minutes": 3},
            {"step_number": 3, "instruction": "Stir-fry vegetables in high heat for 3-4 minutes until tender-crisp.",                                 "technique": "stir-frying", "estimated_minutes": 5},
            {"step_number": 4, "instruction": "Add tofu back in and pour sauce over everything. Toss to coat and serve with rice.",                    "technique": "tossing",     "estimated_minutes": 3},
        ],
    },
    {
        "title": "Classic Caesar Salad",
        "body": "Crisp romaine with a tangy, anchovy-laced Caesar dressing and homemade croutons.",
        "is_draft": False,
        "image_filename": "13.jpg",
        "ingredients": [
            {"name": "romaine lettuce",      "is_animal": False, "is_allergen": False},
            {"name": "anchovy fillets",      "is_animal": True,  "is_allergen": True},
            {"name": "parmesan cheese",      "is_animal": True,  "is_allergen": True},
            {"name": "egg yolk",             "is_animal": True,  "is_allergen": True},
            {"name": "lemon juice",          "is_animal": False, "is_allergen": False},
            {"name": "Dijon mustard",        "is_animal": False, "is_allergen": True},
            {"name": "garlic",               "is_animal": False, "is_allergen": False},
            {"name": "olive oil",            "is_animal": False, "is_allergen": False},
            {"name": "sourdough bread",      "is_animal": False, "is_allergen": True},
            {"name": "Worcestershire sauce", "is_animal": True,  "is_allergen": True},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Tear sourdough into chunks, toss in olive oil and salt, and bake at 375F until golden and crunchy.",              "technique": "baking",       "estimated_minutes": 15},
            {"step_number": 2, "instruction": "Mash anchovies and garlic into a paste. Whisk in egg yolk, lemon juice, mustard, and Worcestershire.",           "technique": "whisking",     "estimated_minutes": 5},
            {"step_number": 3, "instruction": "Slowly drizzle in olive oil while whisking to emulsify into a creamy dressing. Season with salt and pepper.",    "technique": "emulsifying",  "estimated_minutes": 5},
            {"step_number": 4, "instruction": "Toss romaine leaves with dressing, croutons, and shaved parmesan. Serve immediately.",                           "technique": "tossing",      "estimated_minutes": 3},
        ],
    },
]

DUMMY_RECIPES_ = [
    {
        "title": "Classic Margherita Pizza",
        "body": "A simple, delicious Neapolitan-style pizza.",
        "is_draft": False,
        "image_filename": "1.jpg",
        "ingredients": [
            {"name": "00 flour",             "is_animal": False, "is_allergen": True},
            {"name": "fresh mozzarella",     "is_animal": True,  "is_allergen": True},
            {"name": "san marzano tomatoes", "is_animal": False, "is_allergen": False},
            {"name": "fresh basil",          "is_animal": False, "is_allergen": False},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Mix flour, water, salt and yeast. Knead until smooth.",          "technique": "kneading",   "estimated_minutes": 15},
            {"step_number": 2, "instruction": "Stretch dough, add crushed tomatoes and torn mozzarella.",       "technique": "stretching", "estimated_minutes": 10},
            {"step_number": 3, "instruction": "Bake at 500F on a preheated stone for 8-10 minutes.",            "technique": "baking",     "estimated_minutes": 10},
        ],
    },
]

# ── Image upload helper ───────────────────────────────────────────────────────

async def _upload_seed_image(*, recipe_id: int, image_filename: str) -> str | None:
    """
    Reads an image from DUMMY_IMAGE_DIR/<image_filename>, uploads it to S3,
    and returns the resolved URL.  Returns None (with a warning) if the file
    doesn't exist or the upload fails.
    """
    image_path = DUMMY_IMAGE_DIR / image_filename
    if not image_path.exists():
        print(f"[seed] WARNING: image not found, skipping — {image_path}")
        return None

    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        print("[seed] WARNING: S3_BUCKET_NAME not set, skipping image upload")
        return None

    ext = image_path.suffix.lstrip(".").lower() or "jpg"
    key = f"recipes/images/{recipe_id}/{uuid.uuid4().hex}.{ext}"

    content_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    extras = {"ContentType": content_type}
    if not s3.is_local:
        extras["ACL"] = "public-read"

    try:
        with image_path.open("rb") as fh:
            await s3.upload_fileobj(
                Fileobj=fh,
                Key=key,
                ExtraArgs=extras,
            )
    except Exception as exc:
        print(f"[seed] WARNING: failed to upload {image_filename}: {exc}")
        return None

    return f"/api/v1/media/{key}"


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/seed", status_code=201)
async def seed_dummy_recipes(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    if IS_PROD:
        raise HTTPException(status_code=403, detail="Not available in production")

    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admins only")

    inserted = []

    for recipe_data in DUMMY_RECIPES:
        # 1. Recipe row
        recipe = Recipe(
            author_id=user.id,
            title=recipe_data["title"].strip(),
            body=recipe_data["body"],
            parent_id=None,
            is_deleted=False,
            is_locked=False,
            is_draft=recipe_data["is_draft"],
            score=0,
            published_at = datetime.now(timezone.utc),
        )
        session.add(recipe)
        await session.flush()  # populate recipe.id

        # 2. Ingredients
        session.add_all([
            Ingredient(
                recipe_id=recipe.id,
                name=ing["name"].strip(),
                is_animal=ing["is_animal"],
                is_allergen=ing["is_allergen"],
            )
            for ing in recipe_data["ingredients"]
        ])

        # 3. Steps
        session.add_all([
            RecipeStep(
                recipe_id=recipe.id,
                step_number=step["step_number"],
                instruction=step["instruction"].strip(),
                technique=step.get("technique"),
                estimated_minutes=step.get("estimated_minutes") or 0,
            )
            for step in sorted(recipe_data["steps"], key=lambda s: s["step_number"])
        ])

        # 4. Image (best-effort — seeder continues even if this fails)
        image_filename = recipe_data.get("image_filename")
        if image_filename:
            url = await _upload_seed_image(recipe_id=recipe.id, image_filename=image_filename)
            if url:
                session.add(RecipeMedia(
                    recipe_id=recipe.id,
                    media_type=MediaType.IMAGE,
                    url=url,
                    position=0,
                ))

        # 5. Lineage snapshot
        await session.execute(
            insert(RecipeLineageSnapshot)
            .values(recipe_id=recipe.id, root_recipe_id=recipe.id, depth=0)
            .on_conflict_do_nothing(index_elements=["recipe_id"])
        )

        # 6. Activity
        session.add(Activity(
            user_id=user.id,
            verb="recipe.create",
            subject_table="recipes",
            subject_id=recipe.id,
            payload=None,
        ))

        inserted.append({"recipe_id": recipe.id, "title": recipe_data["title"]})

    await session.commit()

    return {
        "ok": True,
        "inserted": len(inserted),
        "recipes": inserted,
    }